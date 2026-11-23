"""
Tests for the transcript loader.
"""
import json
import tempfile
from pathlib import Path

import pytest
from engine.transcript_loader import load_transcript, _load_srt, _load_json
from engine.models import Transcript


SAMPLE_JSON = json.dumps([
    {"word": "Hello", "start": 0.0, "end": 0.5},
    {"word": "world", "start": 0.6, "end": 1.0},
    {"word": "this", "start": 1.1, "end": 1.3},
    {"word": "is", "start": 1.4, "end": 1.5},
    {"word": "a", "start": 1.6, "end": 1.7},
    {"word": "test", "start": 1.8, "end": 2.0},
])

SAMPLE_JSON_DICT = json.dumps({
    "language": "en",
    "words": [
        {"word": "Hello", "start": 0.0, "end": 0.5},
        {"word": "world", "start": 0.6, "end": 1.0},
    ]
})

SAMPLE_SRT = """\
1
00:00:00,000 --> 00:00:02,000
Hello everyone

2
00:00:02,500 --> 00:00:05,000
Welcome to the show
"""


# ---- JSON loading ----

def test_load_json_list():
    t = _load_json(SAMPLE_JSON)
    assert isinstance(t, Transcript)
    assert len(t.words) == 6
    assert t.words[0].word == "Hello"
    assert t.words[0].start == 0.0


def test_load_json_dict():
    t = _load_json(SAMPLE_JSON_DICT)
    assert t.language == "en"
    assert len(t.words) == 2


def test_load_json_phrase_find():
    t = _load_json(SAMPLE_JSON)
    result = t.find_phrase("hello world")
    assert result is not None
    start, end = result
    assert start == 0.0
    assert end == 1.0


def test_load_json_phrase_not_found():
    t = _load_json(SAMPLE_JSON)
    assert t.find_phrase("xyz xyz xyz") is None


# ---- SRT loading ----

def test_load_srt():
    t = _load_srt(SAMPLE_SRT)
    assert len(t.words) > 0
    # First word should be "Hello"
    assert t.words[0].word == "Hello"


def test_load_srt_via_file():
    with tempfile.NamedTemporaryFile(suffix=".srt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(SAMPLE_SRT)
        fname = f.name
    t = load_transcript(fname)
    assert len(t.words) > 0
    Path(fname).unlink()


# ---- Auto-detection ----

def test_load_json_via_file():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
        f.write(SAMPLE_JSON)
        fname = f.name
    t = load_transcript(fname)
    assert len(t.words) == 6
    Path(fname).unlink()


# ---- words_in_range ----

def test_words_in_range():
    t = _load_json(SAMPLE_JSON)
    words = t.words_in_range(0.0, 1.0)
    # Only "Hello" (mid=0.25) and "world" (mid=0.8) are in [0, 1]
    assert len(words) == 2


# ---- duration ----

def test_transcript_duration():
    t = _load_json(SAMPLE_JSON)
    assert t.duration == pytest.approx(2.0)


def test_empty_transcript_duration():
    t = Transcript(words=[])
    assert t.duration == 0.0
