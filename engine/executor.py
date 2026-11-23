"""
Executor: applies a sequence of EditStep objects to produce an FFmpeg
filter-graph string and command-line, then optionally runs it.

Design philosophy
-----------------
- Pure functions where possible; side effects only in `run_ffmpeg`.
- The filter graph is built from scratch each time (history replay).
- Each step kind maps to a small filter-graph fragment.
- Silence/mute uses `volume=enable` with timeline editing.
- Cut/trim uses concat demuxer + select filter.
"""
from __future__ import annotations

import logging
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .models import EditStep, StepKind

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Public API                                                          #
# ------------------------------------------------------------------ #

def execute_step(
    steps: list[EditStep],
    input_path: str,
    output_path: str,
    dry_run: bool = False,
) -> str:
    """
    Build an FFmpeg command for the given *steps* applied to *input_path*,
    write output to *output_path*, and (unless *dry_run*) execute it.

    Returns the FFmpeg command line string.

    Raises
    ------
    subprocess.CalledProcessError
        If FFmpeg exits with a non-zero return code.
    RuntimeError
        If the step list is empty.
    """
    if not steps:
        raise RuntimeError("No steps to execute")

    cmd = build_ffmpeg_command(steps, input_path, output_path)
    logger.debug("FFmpeg command: %s", " ".join(cmd))

    if not dry_run:
        run_ffmpeg(cmd)

    return " ".join(cmd)


def build_ffmpeg_command(
    steps: list[EditStep],
    input_path: str,
    output_path: str,
) -> list[str]:
    """
    Translate a list of EditSteps into an FFmpeg command.

    Parameters
    ----------
    steps:
        Ordered list of resolved edit steps.
    input_path:
        Path to the source video file.
    output_path:
        Desired output file path.

    Returns
    -------
    list[str]
        Argument list suitable for subprocess.run.
    """
    # ---- classify steps ----
    cuts = [s for s in steps if s.kind == StepKind.CUT]
    trims = [s for s in steps if s.kind == StepKind.TRIM]
    silences = [s for s in steps if s.kind == StepKind.SILENCE]
    volumes = [s for s in steps if s.kind == StepKind.VOLUME]
    speeds = [s for s in steps if s.kind == StepKind.SPEED]
    fades = [s for s in steps if s.kind == StepKind.FADE]
    subtitles = [s for s in steps if s.kind == StepKind.SUBTITLE]
    crops = [s for s in steps if s.kind == StepKind.CROP]
    overlays = [s for s in steps if s.kind == StepKind.OVERLAY]

    video_filters: list[str] = []
    audio_filters: list[str] = []

    # ---- TRIM (keep only one range) ----
    if trims:
        # Last trim wins
        t = trims[-1]
        video_filters.append(
            f"trim=start={t.anchor_start}:end={t.anchor_end},setpts=PTS-STARTPTS"
        )
        audio_filters.append(
            f"atrim=start={t.anchor_start}:end={t.anchor_end},asetpts=PTS-STARTPTS"
        )

    # ---- CUT (remove ranges; multiple cuts become a concat) ----
    if cuts:
        select_parts = _build_select_for_cuts(cuts)
        video_filters.append(select_parts["video"])
        audio_filters.append(select_parts["audio"])

    # ---- SILENCE / MUTE ----
    for s in silences:
        a = s.anchor_start
        b = s.anchor_end
        audio_filters.append(
            f"volume=0:enable='between(t,{a},{b})'"
        )

    # ---- VOLUME ----
    for s in volumes:
        db = s.params.get("level_db", 0.0)
        factor = round(10 ** (db / 20), 4)
        a = s.anchor_start
        b = s.anchor_end
        if a is not None and b is not None:
            audio_filters.append(
                f"volume={factor}:enable='between(t,{a},{b})'"
            )
        else:
            audio_filters.append(f"volume={factor}")

    # ---- SPEED ----
    for s in speeds:
        rate = s.params.get("rate", 1.5)
        pts_rate = round(1.0 / rate, 6)
        video_filters.append(f"setpts={pts_rate}*PTS")
        # audio tempo: 0.5–2.0 is the safe range; chain for >2×
        audio_filters.extend(_tempo_chain(rate))

    # ---- FADE ----
    for s in fades:
        direction = s.params.get("direction", "out")
        dur = s.params.get("duration", 1.0)
        video_filters.append(
            f"fade=t={direction}:st=0:d={dur}" if direction == "in"
            else f"fade=t={direction}:st=0:d={dur}"
        )
        audio_filters.append(
            f"afade=t={direction}:st=0:d={dur}"
        )

    # ---- CROP ----
    for s in crops:
        w = s.params.get("aspect_w")
        h = s.params.get("aspect_h")
        if w and h:
            video_filters.append(
                f"crop=ih*{w}/{h}:ih:(iw-ih*{w}/{h})/2:0"
            )

    # ---- SUBTITLE ----
    subtitle_drawtext: list[str] = []
    for s in subtitles:
        text = s.params.get("text", "")
        fs = s.params.get("font_size", 24)
        a = s.anchor_start or 0.0
        b = s.anchor_end or (a + 3.0)
        escaped = text.replace("'", "\\'").replace(":", "\\:")
        subtitle_drawtext.append(
            f"drawtext=text='{escaped}':fontsize={fs}:"
            f"fontcolor=white:x=(w-text_w)/2:y=h-th-20:"
            f"enable='between(t,{a},{b})'"
        )

    video_filters.extend(subtitle_drawtext)

    # ---- Build command ----
    cmd = ["ffmpeg", "-y", "-i", input_path]

    # ---- OVERLAY inputs ----
    for s in overlays:
        path = s.params.get("path", "")
        if path and os.path.exists(path):
            cmd += ["-i", path]

    vf = ",".join(video_filters) if video_filters else None
    af = ",".join(audio_filters) if audio_filters else None

    if vf:
        cmd += ["-vf", vf]
    if af:
        cmd += ["-af", af]

    # Codec options for compatibility
    cmd += [
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path,
    ]

    return cmd


def run_ffmpeg(cmd: list[str]) -> None:
    """Execute the given FFmpeg command and raise on failure."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=result.stderr,
        )


# ------------------------------------------------------------------ #
# Private helpers                                                     #
# ------------------------------------------------------------------ #

def _build_select_for_cuts(cuts: list[EditStep]) -> dict[str, str]:
    """
    Build a select/aselect expression that removes the given ranges.

    The expression keeps every frame that is NOT inside a cut range.
    """
    conditions = []
    for c in cuts:
        a = c.anchor_start
        b = c.anchor_end
        conditions.append(f"not(between(t,{a},{b}))")
    expr = "+".join(conditions)
    return {
        "video": f"select='{expr}',setpts=N/FRAME_RATE/TB",
        "audio": f"aselect='{expr}',asetpts=N/SR/TB",
    }


def _tempo_chain(rate: float) -> list[str]:
    """
    Build an atempo filter chain.  atempo only accepts 0.5–2.0 per stage,
    so rates outside that range need multiple stages.
    """
    filters = []
    r = rate
    while r > 2.0:
        filters.append("atempo=2.0")
        r /= 2.0
    while r < 0.5:
        filters.append("atempo=0.5")
        r /= 0.5
    filters.append(f"atempo={round(r, 6)}")
    return filters
