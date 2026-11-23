"""
Natural-language instruction parser.

Converts a free-text prompt like:
  "Remove everything before 'Welcome to the show'"
  "Cut the section from 1:30 to 2:15"
  "Mute audio between the coughs"
  "Add subtitle 'Chapter 1' at 0:10"

into a structured ParsedInstruction that the planner can resolve against
the transcript and video metadata.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import StepKind


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

_TIME_PATTERNS = [
    # 1:23:45 / 1:23 / 1h23m / 90s / 90.5s / 90
    re.compile(
        r"(?:(?P<h>\d+)h\s*)?(?:(?P<m>\d+)m\s*)?(?P<s>\d+(?:\.\d+)?)s",
        re.IGNORECASE,
    ),
    re.compile(r"(?P<mm>\d+):(?P<ss>\d{2}(?:\.\d+)?)"),
    re.compile(r"(?P<hh>\d+):(?P<mm2>\d{2}):(?P<ss2>\d{2}(?:\.\d+)?)"),
    re.compile(r"\b(?P<raw>\d+(?:\.\d+)?)\s*seconds?\b", re.IGNORECASE),
]


def _parse_time(text: str) -> Optional[float]:
    """
    Try to extract the first timestamp from *text* and return it in seconds.
    Returns None if no timestamp found.
    """
    # HH:MM:SS
    m = re.search(r"\b(\d+):(\d{2}):(\d{2}(?:\.\d+)?)\b", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

    # MM:SS
    m = re.search(r"\b(\d+):(\d{2}(?:\.\d+)?)\b", text)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))

    # 90.5s / 90s
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*s(?:econds?)?\b", text, re.IGNORECASE)
    if m:
        return float(m.group(1))

    # bare number (last resort)
    m = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if m:
        return float(m.group(1))

    return None


def _extract_quoted(text: str) -> Optional[str]:
    """Return the first quoted string found in *text*."""
    m = re.search(r'["\u201c\u201d](.+?)["\u201c\u201d]', text)
    if m:
        return m.group(1)
    # single quotes
    m = re.search(r"'(.+?)'", text)
    if m:
        return m.group(1)
    return None


def _extract_percent(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if m:
        return float(m.group(1))
    return None


def _extract_multiplier(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)[x×]", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


# ------------------------------------------------------------------ #
# Output                                                              #
# ------------------------------------------------------------------ #

@dataclass
class ParsedInstruction:
    """Intermediate representation before anchors are resolved."""
    kind: StepKind = StepKind.UNKNOWN
    # Time anchors (absolute seconds, if given explicitly)
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    # Content anchors (phrase to look up in transcript)
    phrase_start: Optional[str] = None
    phrase_end: Optional[str] = None
    # Additional parameters
    params: dict[str, Any] = field(default_factory=dict)
    # Raw text kept for debugging
    raw: str = ""
    confidence: float = 1.0


# ------------------------------------------------------------------ #
# Main entry point                                                    #
# ------------------------------------------------------------------ #

_TRIM_WORDS = r"\b(trim|keep only|keep from|keep|start from|begin at)\b"
_CUT_WORDS = r"\b(cut|remove|delete|drop|eliminate)\b"
_SILENCE_WORDS = r"\b(mute|silence|silent|quiet|no audio|no sound)\b"
_SUBTITLE_WORDS = r"\b(subtitle|caption|text|label|add text|overlay text)\b"
_CROP_WORDS = r"\b(crop|zoom in|zoom|frame)\b"
_SPEED_WORDS = r"\b(speed up|slow down|faster|slower|accelerate|decelerate|time-lapse|timelapse)\b"
_VOLUME_WORDS = r"\b(volume|louder|quieter|boost audio|lower audio|increase volume|decrease volume)\b"
_FADE_WORDS = r"\b(fade in|fade out|fade)\b"
_OVERLAY_WORDS = r"\b(overlay|watermark|logo|insert image|insert video)\b"
_UNDO_WORDS = r"\b(undo|revert|go back|roll back)\b"
_RESTORE_WORDS = r"\b(restore|jump to step|restore to step)\b"

_BEFORE_WORDS = r"\b(before|until|up to|everything before|up until)\b"
_AFTER_WORDS = r"\b(after|from|everything after|starting from|from the point)\b"
_BETWEEN_WORDS = r"\b(between|from .+ to|from .+ until)\b"


def parse_instruction(text: str) -> ParsedInstruction:
    """
    Parse a natural-language editing instruction.

    >>> parse_instruction("Cut the first 10 seconds")
    ParsedInstruction(kind=<StepKind.CUT: 'cut'>, t_start=0.0, t_end=10.0, ...)

    >>> parse_instruction("Remove everything before 'Welcome back'")
    ParsedInstruction(kind=<StepKind.TRIM: 'trim'>, phrase_start='Welcome back', ...)
    """
    t = text.strip()
    lower = t.lower()
    pi = ParsedInstruction(raw=t)

    # --- UNDO / RESTORE ---
    if re.search(_UNDO_WORDS, lower):
        pi.kind = StepKind.UNDO
        return pi

    if re.search(_RESTORE_WORDS, lower):
        pi.kind = StepKind.RESTORE
        step_ref = _extract_quoted(t)
        if step_ref:
            pi.params["step_id"] = step_ref
        return pi

    # --- TRIM (keep a range) ---
    if re.search(_TRIM_WORDS, lower) or re.search(_BEFORE_WORDS, lower):
        pi.kind = StepKind.TRIM
        # "trim from X to Y" or "keep from X to Y"
        phrase = _extract_quoted(t)
        if phrase:
            if re.search(_BEFORE_WORDS, lower):
                pi.phrase_end = phrase
            elif re.search(_AFTER_WORDS, lower):
                pi.phrase_start = phrase
            else:
                pi.phrase_start = phrase
        else:
            times = _extract_all_times(t)
            if len(times) >= 2:
                pi.t_start, pi.t_end = times[0], times[1]
            elif len(times) == 1:
                if re.search(_BEFORE_WORDS, lower):
                    pi.t_start = 0.0
                    pi.t_end = times[0]
                else:
                    pi.t_start = times[0]
        return pi

    # --- SUBTITLE ---
    if re.search(_SUBTITLE_WORDS, lower):
        pi.kind = StepKind.SUBTITLE
        phrase = _extract_quoted(t)
        if phrase:
            pi.params["text"] = phrase
        m_dur = re.search(r"for\s+(\d+(?:\.\d+)?)\s*s(?:econds?)?", lower)
        dur = float(m_dur.group(1)) if m_dur else None

        times = _extract_all_times(t)
        if times:
            pi.t_start = times[0]
            if dur is not None:
                pi.t_end = pi.t_start + dur
            elif len(times) > 1 and times[1] > times[0]:
                pi.t_end = times[1]
            else:
                pi.t_end = times[0] + 3.0
        # Look for font size
        m = re.search(r"\b(\d+)\s*(?:pt|px|point|pixel)", lower)
        if m:
            pi.params["font_size"] = int(m.group(1))
        return pi

    # --- SILENCE/MUTE ---
    if re.search(_SILENCE_WORDS, lower):
        pi.kind = StepKind.SILENCE
        pi = _resolve_range(pi, t, lower)
        return pi

    # --- CROP ---
    if re.search(_CROP_WORDS, lower):
        pi.kind = StepKind.CROP
        m = re.search(r"(\d+)\s*[:\s×x]\s*(\d+)", lower)
        if m:
            pi.params["aspect_w"] = int(m.group(1))
            pi.params["aspect_h"] = int(m.group(2))
        return pi

    # --- SPEED ---
    if re.search(_SPEED_WORDS, lower):
        pi.kind = StepKind.SPEED
        multiplier = _extract_multiplier(t)
        if multiplier is None:
            if "slow" in lower:
                multiplier = 0.5
            elif "fast" in lower or "time-lapse" in lower:
                multiplier = 2.0
            else:
                multiplier = 1.5
        pi.params["rate"] = multiplier
        pi = _resolve_range(pi, t, lower)
        return pi

    # --- VOLUME ---
    if re.search(_VOLUME_WORDS, lower):
        pi.kind = StepKind.VOLUME
        pct = _extract_percent(t)
        if pct is not None:
            pi.params["level_db"] = round(20 * __import__("math").log10(pct / 100), 1)
        elif "louder" in lower or "boost" in lower or "increase" in lower:
            pi.params["level_db"] = 6.0
        elif "quieter" in lower or "lower" in lower or "decrease" in lower:
            pi.params["level_db"] = -6.0
        pi = _resolve_range(pi, t, lower)
        return pi

    # --- FADE ---
    if re.search(_FADE_WORDS, lower):
        pi.kind = StepKind.FADE
        pi.params["direction"] = "in" if "fade in" in lower else "out"
        times = _extract_all_times(t)
        if times:
            pi.params["duration"] = times[0]
        else:
            pi.params["duration"] = 1.0
        return pi

    # --- OVERLAY ---
    if re.search(_OVERLAY_WORDS, lower):
        pi.kind = StepKind.OVERLAY
        phrase = _extract_quoted(t)
        if phrase:
            pi.params["path"] = phrase
        times = _extract_all_times(t)
        if len(times) >= 2:
            pi.t_start, pi.t_end = times[0], times[1]
        elif len(times) == 1:
            pi.t_start = times[0]
        return pi

    # --- CUT (default for removal language) ---
    if re.search(_CUT_WORDS, lower):
        pi.kind = StepKind.CUT
        pi = _resolve_range(pi, t, lower)
        return pi

    # Fallback: if times are given without a verb, treat as trim
    times = _extract_all_times(t)
    if times:
        pi.kind = StepKind.TRIM
        if len(times) >= 2:
            pi.t_start, pi.t_end = times[0], times[1]
        else:
            pi.t_start = times[0]

    return pi


# ------------------------------------------------------------------ #
# Private helpers                                                     #
# ------------------------------------------------------------------ #

def _extract_all_times(text: str) -> list[float]:
    """Return all timestamps found in text, in order."""
    found: list[tuple[int, float]] = []

    for m in re.finditer(r"\b(\d+):(\d{2}):(\d{2}(?:\.\d+)?)\b", text):
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        found.append((m.start(), t))

    for m in re.finditer(r"\b(\d+):(\d{2}(?:\.\d+)?)\b", text):
        # skip if already covered by HH:MM:SS match
        if not any(abs(m.start() - pos) < 2 for pos, _ in found):
            t = int(m.group(1)) * 60 + float(m.group(2))
            found.append((m.start(), t))

    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*s(?:econds?)?\b", text, re.IGNORECASE):
        if not any(abs(m.start() - pos) < 2 for pos, _ in found):
            found.append((m.start(), float(m.group(1))))

    found.sort()
    return [t for _, t in found]


def _resolve_range(
    pi: ParsedInstruction, text: str, lower: str
) -> ParsedInstruction:
    """Fill t_start / t_end / phrase_start / phrase_end from the text."""
    phrases = re.findall(r'["\u201c\u201d](.+?)["\u201c\u201d]|\'(.+?)\'', text)
    flat_phrases = [a or b for a, b in phrases]

    if flat_phrases:
        if re.search(_BETWEEN_WORDS, lower):
            pi.phrase_start = flat_phrases[0] if flat_phrases else None
            pi.phrase_end = flat_phrases[1] if len(flat_phrases) > 1 else None
        elif re.search(_BEFORE_WORDS, lower):
            pi.t_start = 0.0
            pi.phrase_end = flat_phrases[0]
        elif re.search(_AFTER_WORDS, lower):
            pi.phrase_start = flat_phrases[0]
        else:
            pi.phrase_start = flat_phrases[0]
            pi.phrase_end = flat_phrases[1] if len(flat_phrases) > 1 else None
    else:
        times = _extract_all_times(text)
        if len(times) >= 2:
            pi.t_start, pi.t_end = times[0], times[1]
        elif len(times) == 1:
            if re.search(_BEFORE_WORDS, lower):
                pi.t_start = 0.0
                pi.t_end = times[0]
            elif re.search(_AFTER_WORDS, lower):
                pi.t_start = times[0]
            else:
                pi.t_start = 0.0
                pi.t_end = times[0]

    return pi
