"""
Metric measurement script.

Run this after setting up the project to generate numbers for REPORT.md
and the Excel submission form.

Usage:
    python tools/measure_metrics.py

Requires: the engine package to be importable (run from the repo root).
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.parser import parse_instruction
from engine.planner import plan_edit
from engine.models import EditSession, Transcript, TranscriptWord


def _make_transcript() -> Transcript:
    words = [
        TranscriptWord(f"word{i}", i * 0.5, i * 0.5 + 0.4)
        for i in range(40)
    ]
    return Transcript(words=words)


def measure_parse_latency(n: int = 1000) -> dict:
    instructions = [
        "Keep from 0:30 to 1:45",
        "Cut from 1:00 to 2:00",
        "Remove everything before 'Welcome back'",
        "Mute audio from 0:30 to 0:45",
        "Add subtitle 'Chapter 1' at 0:10",
        "Speed up 2x",
        "Make the audio louder",
        "Fade in over 2 seconds",
        "Undo",
        "Crop to 16:9",
    ]
    times = []
    for i in range(n):
        instruction = instructions[i % len(instructions)]
        t0 = time.perf_counter()
        parse_instruction(instruction)
        times.append((time.perf_counter() - t0) * 1000)  # ms

    return {
        "n": n,
        "p50_ms": round(statistics.median(times), 3),
        "p99_ms": round(sorted(times)[int(n * 0.99)], 3),
        "mean_ms": round(statistics.mean(times), 3),
        "max_ms": round(max(times), 3),
    }


def measure_plan_latency(n: int = 1000) -> dict:
    session = EditSession()
    session.transcript = _make_transcript()
    instructions = [
        "Keep from 2.0s to 15.0s",
        "Mute from 5.0s to 10.0s",
        "Add subtitle 'Hello' at 1.0s for 3.0s",
    ]
    times = []
    for i in range(n):
        instruction = instructions[i % len(instructions)]
        pi = parse_instruction(instruction)
        t0 = time.perf_counter()
        try:
            plan_edit(session, pi, video_duration=20.0)
        except Exception:
            pass
        times.append((time.perf_counter() - t0) * 1000)

    return {
        "n": n,
        "p50_ms": round(statistics.median(times), 3),
        "p99_ms": round(sorted(times)[int(n * 0.99)], 3),
        "mean_ms": round(statistics.mean(times), 3),
        "max_ms": round(max(times), 3),
    }


def main() -> None:
    print("=" * 60)
    print("IncuBrix PS2 — Metric Measurement")
    print("=" * 60)

    print("\n[1/2] Parsing latency (1000 iterations):")
    p = measure_parse_latency(1000)
    print(f"  p50 : {p['p50_ms']} ms")
    print(f"  p99 : {p['p99_ms']} ms")
    print(f"  mean: {p['mean_ms']} ms")
    print(f"  max : {p['max_ms']} ms")

    print("\n[2/2] Planning latency (1000 iterations):")
    pl = measure_plan_latency(1000)
    print(f"  p50 : {pl['p50_ms']} ms")
    print(f"  p99 : {pl['p99_ms']} ms")
    print(f"  mean: {pl['mean_ms']} ms")
    print(f"  max : {pl['max_ms']} ms")

    print("\n[Paste these numbers into REPORT.md §3 and the Excel 5_Metrics sheet]")


if __name__ == "__main__":
    main()
