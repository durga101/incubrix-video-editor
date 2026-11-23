"""
CLI session runner.

Runs a YAML-defined session against either the local engine (--local) or
the HTTP API (--api URL) and reports pass/fail for each session step.

Usage
-----
    # Local mode (no server required)
    python -m cli.session_runner sessions/ --local --out out/

    # API mode (server must be running)
    python -m cli.session_runner sessions/ --api http://localhost:8000 --render --out out_api/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

# ------------------------------------------------------------------ #
# Entry point                                                         #
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(description="IncuBrix session runner")
    parser.add_argument("sessions_dir", help="Directory containing session YAML files")
    parser.add_argument("--local", action="store_true", help="Run against local engine")
    parser.add_argument("--api", metavar="URL", help="Run against HTTP API at URL")
    parser.add_argument("--render", action="store_true", help="Trigger render after session")
    parser.add_argument("--out", metavar="DIR", default="out", help="Output directory")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    session_files = sorted(sessions_dir.glob("*.yaml")) + sorted(sessions_dir.glob("*.yml"))
    if not session_files:
        print(f"No YAML files found in {sessions_dir}")
        sys.exit(1)

    total = 0
    passed = 0

    for sf in session_files:
        total += 1
        try:
            result = run_session_file(sf, args, out_dir)
            status = "PASS" if result["ok"] else "FAIL"
            if result["ok"]:
                passed += 1
        except Exception as exc:
            status = "FAIL"
            result = {"ok": False, "error": str(exc)}

        print(f"[{status}] {sf.name}  —  {result.get('summary', result.get('error', ''))}")

        # Save result
        out_file = out_dir / (sf.stem + "_result.json")
        out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\n{passed}/{total} sessions passed.")
    sys.exit(0 if passed == total else 1)


def run_session_file(path: Path, args, out_dir: Path) -> dict:
    """Execute one session YAML and return a result dict."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    name = data.get("name", path.stem)
    steps = data.get("steps", [])

    if args.local:
        return _run_local(name, steps, data, out_dir)
    elif args.api:
        return _run_api(name, steps, data, args.api, args.render, out_dir)
    else:
        raise ValueError("Specify --local or --api URL")


# ------------------------------------------------------------------ #
# Local runner                                                        #
# ------------------------------------------------------------------ #

def _run_local(name: str, steps: list, meta: dict, out_dir: Path) -> dict:
    from engine.models import EditSession
    from engine.parser import parse_instruction
    from engine.planner import plan_edit
    from engine.history import EditHistory
    from engine.transcript_loader import load_transcript

    session = EditSession()

    # Load transcript if specified
    transcript_path = meta.get("transcript")
    if transcript_path:
        tp = Path(transcript_path)
        if tp.exists():
            session.transcript = load_transcript(tp)

    history = EditHistory(session)
    results = []
    ok = True

    for s in steps:
        instruction = s.get("instruction", "")
        expected_kind = s.get("expect_kind")
        expect_error = s.get("expect_error", False)

        try:
            pi = parse_instruction(instruction)
            step = plan_edit(session, pi)
            history.apply(step)
            step_result = {
                "instruction": instruction,
                "kind": step.kind.value,
                "anchor_start": step.anchor_start,
                "anchor_end": step.anchor_end,
                "ok": True,
            }
            if expected_kind and step.kind.value != expected_kind:
                step_result["ok"] = False
                step_result["error"] = f"Expected kind {expected_kind!r}, got {step.kind.value!r}"
                ok = False
            if expect_error:
                step_result["ok"] = False
                step_result["error"] = "Expected an error but none occurred"
                ok = False
        except Exception as exc:
            step_result = {
                "instruction": instruction,
                "ok": expect_error,  # ok if we expected an error
                "error": str(exc),
            }
            if not expect_error:
                ok = False

        results.append(step_result)

    return {
        "name": name,
        "ok": ok,
        "steps": results,
        "summary": f"{sum(1 for r in results if r['ok'])}/{len(results)} steps OK",
        "history": history.as_dict(),
    }


# ------------------------------------------------------------------ #
# API runner                                                          #
# ------------------------------------------------------------------ #

def _run_api(
    name: str,
    steps: list,
    meta: dict,
    api_url: str,
    do_render: bool,
    out_dir: Path,
) -> dict:
    try:
        import httpx
    except ImportError:
        raise RuntimeError(
            "httpx is required for API mode: pip install httpx"
        )

    base = api_url.rstrip("/")
    results = []
    ok = True

    # Create session
    r = httpx.post(f"{base}/sessions")
    r.raise_for_status()
    session_id = r.json()["session_id"]

    # Upload video + transcript if present
    video_path = meta.get("video")
    transcript_path = meta.get("transcript")
    if video_path and Path(video_path).exists():
        files = {"video": open(video_path, "rb")}
        if transcript_path and Path(transcript_path).exists():
            files["transcript"] = open(transcript_path, "rb")
        r = httpx.post(f"{base}/sessions/{session_id}/upload", files=files, timeout=60.0)
        r.raise_for_status()

    # Apply steps
    for s in steps:
        instruction = s.get("instruction", "")
        expected_kind = s.get("expect_kind")
        expect_error = s.get("expect_error", False)

        try:
            r = httpx.post(
                f"{base}/sessions/{session_id}/edit",
                json={"instruction": instruction, "dry_run": not do_render},
                timeout=30.0,
            )
            if expect_error:
                step_ok = r.status_code >= 400
                step_result = {
                    "instruction": instruction,
                    "ok": step_ok,
                    "status_code": r.status_code,
                }
            else:
                r.raise_for_status()
                body = r.json()
                step_result = {
                    "instruction": instruction,
                    "kind": body.get("kind"),
                    "anchor_start": body.get("anchor_start"),
                    "anchor_end": body.get("anchor_end"),
                    "ok": True,
                }
                if expected_kind and body.get("kind") != expected_kind:
                    step_result["ok"] = False
                    step_result["error"] = (
                        f"Expected {expected_kind!r}, got {body.get('kind')!r}"
                    )
                    ok = False
        except Exception as exc:
            step_result = {
                "instruction": instruction,
                "ok": expect_error,
                "error": str(exc),
            }
            if not expect_error:
                ok = False

        results.append(step_result)

    # Optional render
    render_result = None
    if do_render:
        try:
            r = httpx.post(
                f"{base}/render/{session_id}",
                json={"output_format": "mp4"},
                timeout=10.0,
            )
            r.raise_for_status()
            job = r.json()
            job_id = job["job_id"]

            # Poll until done
            for _ in range(60):
                time.sleep(2)
                r = httpx.get(f"{base}/render/{session_id}/{job_id}")
                r.raise_for_status()
                poll = r.json()
                if poll["status"] in ("done", "failed"):
                    render_result = poll
                    break
        except Exception as exc:
            render_result = {"ok": False, "error": str(exc)}

    return {
        "name": name,
        "session_id": session_id,
        "ok": ok,
        "steps": results,
        "render": render_result,
        "summary": f"{sum(1 for r in results if r['ok'])}/{len(results)} steps OK",
    }


if __name__ == "__main__":
    main()
