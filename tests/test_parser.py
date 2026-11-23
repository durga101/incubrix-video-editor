"""Tests for the natural-language parser."""
import pytest
from engine.parser import parse_instruction
from engine.models import StepKind


# ---- TRIM ----

def test_parse_trim_times():
    pi = parse_instruction("Keep from 0:30 to 1:45")
    assert pi.kind == StepKind.TRIM
    assert pi.t_start == 30.0
    assert pi.t_end == 105.0


def test_parse_trim_phrase_start():
    pi = parse_instruction("Start from 'Welcome back'")
    assert pi.kind == StepKind.TRIM
    assert pi.phrase_start == "Welcome back"


def test_parse_trim_before_phrase():
    pi = parse_instruction('Keep everything before "That is all for today"')
    assert pi.kind == StepKind.TRIM
    assert pi.phrase_end == "That is all for today"


def test_parse_trim_seconds():
    pi = parse_instruction("Keep from 0s to 60s")
    assert pi.kind == StepKind.TRIM
    assert pi.t_end == 60.0


# ---- CUT ----

def test_parse_cut_times():
    pi = parse_instruction("Cut from 1:00 to 2:00")
    assert pi.kind == StepKind.CUT
    assert pi.t_start == 60.0
    assert pi.t_end == 120.0


def test_parse_cut_remove_first():
    pi = parse_instruction("Remove the first 10 seconds")
    assert pi.kind == StepKind.CUT


def test_parse_cut_between_phrases():
    pi = parse_instruction("Remove everything between 'uh' and 'anyway'")
    assert pi.kind == StepKind.CUT
    assert pi.phrase_start == "uh"
    assert pi.phrase_end == "anyway"


def test_parse_delete():
    pi = parse_instruction("Delete from 0:05 to 0:10")
    assert pi.kind == StepKind.CUT


# ---- SILENCE / MUTE ----

def test_parse_silence_times():
    pi = parse_instruction("Mute audio from 0:30 to 0:45")
    assert pi.kind == StepKind.SILENCE
    assert pi.t_start == 30.0
    assert pi.t_end == 45.0


def test_parse_silence_phrase():
    pi = parse_instruction("Silence 'uh' to 'sorry'")
    assert pi.kind == StepKind.SILENCE


def test_parse_mute():
    pi = parse_instruction("Quiet the audio between 1:00 and 1:10")
    assert pi.kind == StepKind.SILENCE


# ---- SUBTITLE ----

def test_parse_subtitle_basic():
    pi = parse_instruction("Add subtitle 'Chapter 1' at 0:10")
    assert pi.kind == StepKind.SUBTITLE
    assert pi.params["text"] == "Chapter 1"
    assert pi.t_start == 10.0


def test_parse_subtitle_range():
    pi = parse_instruction("Caption 'Introduction' from 0:05 to 0:15")
    assert pi.kind == StepKind.SUBTITLE
    assert pi.params["text"] == "Introduction"
    assert pi.t_start == 5.0
    assert pi.t_end == 15.0


def test_parse_drawtext():
    pi = parse_instruction("Add text 'Hello world' at 1:00 for 5 seconds")
    assert pi.kind == StepKind.SUBTITLE
    assert pi.params["text"] == "Hello world"


# ---- SPEED ----

def test_parse_speed_fast():
    pi = parse_instruction("Speed up 2x")
    assert pi.kind == StepKind.SPEED
    assert pi.params["rate"] == 2.0


def test_parse_speed_slow():
    pi = parse_instruction("Slow down to 0.5x")
    assert pi.kind == StepKind.SPEED
    assert pi.params["rate"] == 0.5


def test_parse_timelapse():
    pi = parse_instruction("Make it a timelapse")
    assert pi.kind == StepKind.SPEED


# ---- VOLUME ----

def test_parse_volume_louder():
    pi = parse_instruction("Make the audio louder")
    assert pi.kind == StepKind.VOLUME
    assert pi.params["level_db"] > 0


def test_parse_volume_quieter():
    pi = parse_instruction("Lower the volume")
    assert pi.kind == StepKind.VOLUME
    assert pi.params["level_db"] < 0


def test_parse_volume_percent():
    pi = parse_instruction("Set volume to 50%")
    assert pi.kind == StepKind.VOLUME
    # 50% = -6 dB approximately
    assert pi.params["level_db"] < 0


# ---- FADE ----

def test_parse_fade_in():
    pi = parse_instruction("Add a 2 second fade in")
    assert pi.kind == StepKind.FADE
    assert pi.params["direction"] == "in"
    assert pi.params["duration"] == 2.0


def test_parse_fade_out():
    pi = parse_instruction("Fade out at the end")
    assert pi.kind == StepKind.FADE
    assert pi.params["direction"] == "out"


# ---- CROP ----

def test_parse_crop_ratio():
    pi = parse_instruction("Crop to 16:9")
    assert pi.kind == StepKind.CROP
    assert pi.params["aspect_w"] == 16
    assert pi.params["aspect_h"] == 9


# ---- UNDO / RESTORE ----

def test_parse_undo():
    pi = parse_instruction("Undo")
    assert pi.kind == StepKind.UNDO


def test_parse_undo_last():
    pi = parse_instruction("Undo the last step")
    assert pi.kind == StepKind.UNDO


def test_parse_revert():
    pi = parse_instruction("Revert")
    assert pi.kind == StepKind.UNDO


def test_parse_restore():
    pi = parse_instruction("Restore to step 'abc-123'")
    assert pi.kind == StepKind.RESTORE


# ---- UNKNOWN / EDGE CASES ----

def test_parse_empty_returns_unknown():
    pi = parse_instruction("")
    # Should not crash; kind may be UNKNOWN
    assert pi.kind is not None


def test_parse_gibberish_does_not_crash():
    pi = parse_instruction("xyzzy frobnicate the wumpus")
    assert pi is not None


def test_parse_hms_time():
    pi = parse_instruction("Cut from 1:02:03 to 1:02:30")
    assert pi.kind == StepKind.CUT
    assert pi.t_start == pytest.approx(3723.0)
    assert pi.t_end == pytest.approx(3750.0)
