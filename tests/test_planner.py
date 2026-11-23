"""Tests for the edit planner."""
import pytest
from engine.models import EditSession, StepKind, Transcript, TranscriptWord
from engine.parser import parse_instruction
from engine.planner import plan_edit


def _make_transcript() -> Transcript:
    words = [
        TranscriptWord("Hello", 0.0, 0.5),
        TranscriptWord("everyone", 0.6, 1.0),
        TranscriptWord("welcome", 2.0, 2.4),   # silence gap before this
        TranscriptWord("back", 2.5, 2.8),
        TranscriptWord("to", 2.9, 3.0),
        TranscriptWord("the", 3.1, 3.2),
        TranscriptWord("show", 3.3, 3.8),
        TranscriptWord("today", 5.0, 5.4),     # gap 3.8–5.0
        TranscriptWord("we", 5.5, 5.7),
        TranscriptWord("discuss", 5.8, 6.3),
        TranscriptWord("coding", 6.4, 6.9),
        TranscriptWord("goodbye", 9.0, 9.4),   # gap before this
    ]
    return Transcript(words=words)


def _session(transcript=True) -> EditSession:
    s = EditSession()
    if transcript:
        s.transcript = _make_transcript()
    return s


# ---- Basic resolution ----

def test_plan_trim_times():
    session = _session()
    pi = parse_instruction("Keep from 2.0s to 5.0s")
    step = plan_edit(session, pi, video_duration=10.0)
    assert step.kind == StepKind.TRIM
    assert step.anchor_start < step.anchor_end


def test_plan_cut_times():
    session = _session()
    pi = parse_instruction("Cut from 1:00 to 2:00")
    step = plan_edit(session, pi, video_duration=180.0)
    assert step.kind == StepKind.CUT
    assert step.anchor_start == pytest.approx(60.0, abs=1.0)
    assert step.anchor_end == pytest.approx(120.0, abs=1.0)


def test_plan_phrase_found():
    session = _session()
    pi = parse_instruction("Start from 'welcome back'")
    step = plan_edit(session, pi, video_duration=10.0)
    assert step.kind == StepKind.TRIM
    assert step.anchor_start is not None
    assert step.anchor_start >= 0.0


def test_plan_phrase_not_found_raises():
    session = _session()
    pi = parse_instruction("Cut 'this phrase is not in the transcript'")
    pi.phrase_start = "this phrase is not in the transcript"
    with pytest.raises(ValueError, match="not found in transcript"):
        plan_edit(session, pi, video_duration=10.0)


def test_plan_clamp_to_duration():
    session = _session(transcript=False)
    pi = parse_instruction("Cut from 50s to 200s")
    step = plan_edit(session, pi, video_duration=100.0)
    assert step.anchor_end <= 100.0


def test_plan_snap_to_silence():
    """When snap_to_silence=True the anchor should land in a silence gap."""
    session = _session()
    pi = parse_instruction("Cut from 1.5s to 4.5s")  # between gaps
    step = plan_edit(session, pi, video_duration=10.0)
    # Snap should move start toward gap at 1.0–2.0 (after "everyone", before "welcome")
    assert step.anchor_start < 2.0
    assert step.anchor_end is not None


def test_plan_no_transcript_still_works():
    session = _session(transcript=False)
    pi = parse_instruction("Mute from 0:10 to 0:20")
    step = plan_edit(session, pi, video_duration=60.0)
    assert step.kind == StepKind.SILENCE
    assert step.anchor_start == pytest.approx(10.0, abs=0.5)


def test_plan_subtitle():
    session = _session()
    pi = parse_instruction("Add subtitle 'Chapter 1' at 0:10")
    step = plan_edit(session, pi)
    assert step.kind == StepKind.SUBTITLE
    assert step.params["text"] == "Chapter 1"


def test_plan_undo_passthrough():
    session = _session()
    pi = parse_instruction("Undo")
    step = plan_edit(session, pi)
    assert step.kind == StepKind.UNDO


def test_plan_speed():
    session = _session()
    pi = parse_instruction("Speed up 2x")
    step = plan_edit(session, pi, video_duration=60.0)
    assert step.kind == StepKind.SPEED
    assert step.params["rate"] == 2.0


def test_plan_empty_range_raises():
    """t_start >= t_end should raise ValueError."""
    session = _session(transcript=False)
    pi = parse_instruction("Cut from 5.0s to 5.0s")
    # Both map to the same second → invalid range
    with pytest.raises(ValueError, match="empty or invalid"):
        plan_edit(session, pi, video_duration=60.0)
