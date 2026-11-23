"""
Transcript loader: reads word-level transcript files in multiple formats.

Supported formats
-----------------
1. JSON — IncuBrix standard format (list of {word, start, end, [speaker]})
2. SRT  — standard subtitle format (word-granularity not guaranteed;
           phrase-level timing is used instead)
3. VTT  — WebVTT subtitle format
4. Plain text — no timing; used as fallback for subtitle generation only
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .models import Transcript, TranscriptWord


def load_transcript(path: str | Path) -> Transcript:
    """
    Auto-detect format and load a transcript from *path*.

    Returns
    -------
    Transcript
        Populated with word-level timing where available.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    text = p.read_text(encoding="utf-8", errors="replace")

    if suffix == ".json":
        return _load_json(text)
    if suffix == ".srt":
        return _load_srt(text)
    if suffix == ".vtt":
        return _load_vtt(text)
    # Try JSON anyway
    try:
        return _load_json(text)
    except Exception:
        pass
    return Transcript(words=[], source="unknown")


def _load_json(text: str) -> Transcript:
    """
    Expected shape:

    .. code-block:: json

        [
          {"word": "Hello", "start": 0.1, "end": 0.5, "speaker": "A"},
          ...
        ]

    or

    .. code-block:: json

        {
          "words": [...],
          "language": "en"
        }
    """
    data = json.loads(text)

    if isinstance(data, list):
        words_data = data
        language = "en"
    elif isinstance(data, dict):
        words_data = data.get("words", [])
        language = data.get("language", "en")
    else:
        raise ValueError(f"Unexpected JSON root type: {type(data)}")

    words = []
    for w in words_data:
        words.append(
            TranscriptWord(
                word=str(w.get("word", w.get("text", ""))),
                start=float(w.get("start", 0.0)),
                end=float(w.get("end", 0.0)),
                speaker=w.get("speaker"),
                confidence=float(w.get("confidence", 1.0)),
            )
        )

    return Transcript(words=words, language=language, source="json")


def _load_srt(text: str) -> Transcript:
    """Parse SRT subtitle file into Transcript (phrase-level timing)."""
    blocks = re.split(r"\n\n+", text.strip())
    words: list[TranscriptWord] = []

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        # Line 0: index; Line 1: timestamps; Line 2+: text
        try:
            start, end = _parse_srt_time(lines[1])
        except Exception:
            continue
        phrase = " ".join(lines[2:]).strip()
        # Split into pseudo-words with evenly distributed timing
        tokens = phrase.split()
        if not tokens:
            continue
        dur = (end - start) / len(tokens)
        for i, tok in enumerate(tokens):
            words.append(
                TranscriptWord(
                    word=tok,
                    start=round(start + i * dur, 3),
                    end=round(start + (i + 1) * dur, 3),
                    confidence=0.8,
                )
            )

    return Transcript(words=words, source="srt")


def _parse_srt_time(s: str) -> tuple[float, float]:
    """Parse '00:01:23,456 --> 00:01:25,789' into (start_s, end_s)."""
    m = re.match(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)",
        s.strip(),
    )
    if not m:
        raise ValueError(f"Cannot parse SRT time: {s!r}")
    h1, m1, s1, ms1 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    h2, m2, s2, ms2 = int(m.group(5)), int(m.group(6)), int(m.group(7)), int(m.group(8))
    start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
    end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
    return start, end


def _load_vtt(text: str) -> Transcript:
    """Parse WebVTT — same logic as SRT after stripping the WEBVTT header."""
    # Remove WEBVTT header and NOTE blocks
    cleaned = re.sub(r"^WEBVTT.*?\n", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"NOTE[^\n]*\n.*?\n\n", "", cleaned, flags=re.DOTALL)
    # VTT uses --> with optional position cues
    srt_like = re.sub(
        r"(\d+:\d+:\d+\.\d+)\s*-->\s*(\d+:\d+:\d+\.\d+)[^\n]*",
        lambda m: f"{m.group(1).replace('.', ',')} --> {m.group(2).replace('.', ',')}",
        cleaned,
    )
    # Inject fake block numbers so the SRT parser is happy
    numbered = re.sub(
        r"\n(\d+:\d+)", lambda m, c=iter(range(1, 9999)): f"\n{next(c)}\n{m.group(1)}", srt_like
    )
    return _load_srt(numbered)
