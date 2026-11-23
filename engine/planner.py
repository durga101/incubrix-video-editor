"""
Planner: resolves a ParsedInstruction against the session context
(transcript, video duration) and returns a fully-specified EditStep.

Key responsibilities
--------------------
1. Content-anchored edits: convert phrase references to timestamps.
2. Snap-to-silence: nudge cut points to the nearest silence boundary.
3. Clamp to video duration.
4. Validate parameters and produce human-readable plan summaries.
"""
from __future__ import annotations

import logging
from typing import Optional

from .models import EditSession, EditStep, StepKind, Transcript
from .parser import ParsedInstruction

logger = logging.getLogger(__name__)

# Max seconds to snap a cut edge toward a silence boundary
_SNAP_RADIUS = 0.5


def plan_edit(
    session: EditSession,
    pi: ParsedInstruction,
    video_duration: Optional[float] = None,
) -> EditStep:
    """
    Resolve *pi* into an :class:`EditStep` using the session context.

    Parameters
    ----------
    session:
        Current edit session (provides transcript if available).
    pi:
        Output of :func:`~engine.parser.parse_instruction`.
    video_duration:
        Duration of the source video in seconds.  Used for clamping and
        computing "end-of-file" anchors.  If None, clamping is skipped.

    Returns
    -------
    EditStep
        Fully resolved step ready to be appended to the session history.

    Raises
    ------
    ValueError
        If the instruction cannot be resolved (e.g., phrase not found in
        transcript when no fallback is available).
    """
    step = EditStep(
        kind=pi.kind,
        params=dict(pi.params),
        raw_instruction=pi.raw,
        snap_to_silence=True,
    )

    # Passthrough for session-management operations
    if pi.kind in (StepKind.UNDO, StepKind.RESTORE):
        return step

    if pi.kind == StepKind.UNKNOWN or not pi.raw.strip():
        raise ValueError("Cannot plan empty or unknown instruction")

    transcript = session.transcript
    dur = video_duration

    # ------------------------------------------------------------------ #
    # 1. Resolve phrase anchors → timestamps                              #
    # ------------------------------------------------------------------ #
    t_start = pi.t_start
    t_end = pi.t_end

    if pi.phrase_start is not None:
        result = _find_phrase(pi.phrase_start, transcript)
        if result is None:
            raise ValueError(
                f"Phrase not found in transcript: {pi.phrase_start!r}"
            )
        t_start = result[0]

    if pi.phrase_end is not None:
        result = _find_phrase(pi.phrase_end, transcript)
        if result is None:
            raise ValueError(
                f"Phrase not found in transcript: {pi.phrase_end!r}"
            )
        t_end = result[1]

    # ------------------------------------------------------------------ #
    # 2. Defaults                                                         #
    # ------------------------------------------------------------------ #
    if t_start is None:
        t_start = 0.0
    if t_end is None:
        if dur is not None:
            t_end = dur
        else:
            t_end = t_start + 10.0  # arbitrary fallback

    # ------------------------------------------------------------------ #
    # 3. Snap to silence                                                  #
    # ------------------------------------------------------------------ #
    if transcript and step.snap_to_silence:
        t_start = _snap_to_silence(t_start, transcript, prefer="start")
        t_end = _snap_to_silence(t_end, transcript, prefer="end")

    # ------------------------------------------------------------------ #
    # 4. Clamp to [0, duration]                                           #
    # ------------------------------------------------------------------ #
    t_start = max(0.0, t_start)
    if dur is not None:
        t_end = min(dur, t_end)

    if t_start >= t_end:
        raise ValueError(
            f"Resolved time range is empty or invalid: "
            f"[{t_start:.2f}s, {t_end:.2f}s]"
        )

    step.anchor_start = round(t_start, 3)
    step.anchor_end = round(t_end, 3)

    logger.debug(
        "Planned %s [%.3f – %.3f] from instruction: %r",
        step.kind.value,
        step.anchor_start,
        step.anchor_end,
        pi.raw,
    )
    return step


# ------------------------------------------------------------------ #
# Private helpers                                                     #
# ------------------------------------------------------------------ #

def _find_phrase(phrase: str, transcript: Optional[Transcript]) -> Optional[tuple[float, float]]:
    if transcript is None:
        return None
    result = transcript.find_phrase(phrase)
    if result is None:
        logger.warning("Phrase not found in transcript: %r", phrase)
    return result


def _snap_to_silence(
    t: float,
    transcript: Transcript,
    prefer: str = "start",
) -> float:
    """
    Move *t* to the nearest gap between words, within _SNAP_RADIUS seconds.

    Strategy:
    - Build a list of silence intervals from gaps between consecutive words.
    - Find the gap whose midpoint is closest to *t*.
    - If the gap midpoint is within _SNAP_RADIUS, snap *t* to the gap
      midpoint (or its start/end edge depending on `prefer`).
    """
    words = transcript.words
    if len(words) < 2:
        return t

    gaps: list[tuple[float, float]] = []
    for i in range(len(words) - 1):
        gap_start = words[i].end
        gap_end = words[i + 1].start
        if gap_end > gap_start + 0.05:   # ignore tiny artefact gaps < 50 ms
            gaps.append((gap_start, gap_end))

    if not gaps:
        return t

    best_gap: Optional[tuple[float, float]] = None
    best_dist = float("inf")
    for gs, ge in gaps:
        mid = (gs + ge) / 2
        dist = abs(mid - t)
        if dist < best_dist:
            best_dist = dist
            best_gap = (gs, ge)

    if best_dist <= _SNAP_RADIUS and best_gap:
        gs, ge = best_gap
        if prefer == "start":
            return gs
        elif prefer == "end":
            return ge
        else:
            return (gs + ge) / 2

    return t
