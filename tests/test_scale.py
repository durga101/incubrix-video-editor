"""Additional scale / edge-case tests."""
import pytest
from engine.parser import parse_instruction
from engine.planner import plan_edit
from engine.history import EditHistory
from engine.models import EditSession, StepKind
from tests.scenario_data import make_session_with_transcript


# ---- Chained edits ----

def test_multiple_cuts_accumulate():
    session = make_session_with_transcript()
    h = EditHistory(session)
    for instruction in [
        "Cut from 0:00 to 0:01",
        "Cut from 0:05 to 0:06",
        "Cut from 0:10 to 0:11",
    ]:
        pi = parse_instruction(instruction)
        step = plan_edit(session, pi, video_duration=90.0)
        h.apply(step)
    assert h.step_count == 3


def test_undo_all():
    session = make_session_with_transcript()
    h = EditHistory(session)
    for instruction in ["Cut from 0:30 to 0:40", "Mute from 0:10 to 0:20"]:
        pi = parse_instruction(instruction)
        step = plan_edit(session, pi, video_duration=90.0)
        h.apply(step)
    h.undo()
    h.undo()
    assert h.step_count == 0


def test_undo_beyond_history():
    session = EditSession()
    h = EditHistory(session)
    result = h.undo()
    assert result is None


def test_phrase_anchor_cut():
    session = make_session_with_transcript()
    pi = parse_instruction("Cut 'uh'")
    pi.phrase_start = "uh"
    pi.kind = StepKind.CUT
    step = plan_edit(session, pi, video_duration=90.0)
    assert step.anchor_start is not None


def test_phrase_anchor_trim_start():
    session = make_session_with_transcript()
    pi = parse_instruction("Start from 'today we are'")
    step = plan_edit(session, pi, video_duration=90.0)
    assert step.anchor_start is not None
    # Should be around 5.1s where "today" appears
    assert step.anchor_start < 10.0


def test_phrase_trim_end():
    session = make_session_with_transcript()
    pi = parse_instruction("Keep everything before 'That is all'")
    step = plan_edit(session, pi, video_duration=90.0)
    # phrase "That is all" starts around 20.1s
    assert step.anchor_end is not None
    assert step.anchor_end < 25.0


def test_subtitle_no_time_defaults():
    session = EditSession()
    pi = parse_instruction("Add subtitle 'Intro' at 0:00")
    step = plan_edit(session, pi)
    assert step.kind == StepKind.SUBTITLE
    # Should default to t=0 with some duration
    assert step.anchor_start == 0.0
    assert step.anchor_end is not None
    assert step.anchor_end > step.anchor_start


def test_volume_range():
    session = EditSession()
    pi = parse_instruction("Louder from 0:10 to 0:30")
    step = plan_edit(session, pi, video_duration=60.0)
    assert step.kind == StepKind.VOLUME


def test_fade_default_duration():
    session = EditSession()
    pi = parse_instruction("Fade in")
    step = plan_edit(session, pi, video_duration=60.0)
    assert step.kind == StepKind.FADE
    assert step.params.get("duration", 1.0) >= 0.5


def test_no_video_duration_still_plans():
    """Plan should not raise when video_duration is None."""
    session = make_session_with_transcript()
    pi = parse_instruction("Mute from 0:05 to 0:10")
    step = plan_edit(session, pi, video_duration=None)
    assert step.anchor_start is not None
