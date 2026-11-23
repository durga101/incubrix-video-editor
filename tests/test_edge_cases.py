"""Comprehensive edge-case and robustness tests."""
import pytest
from engine.models import EditSession, EditStep, StepKind, Transcript, TranscriptWord
from engine.parser import parse_instruction
from engine.planner import plan_edit, _snap_to_silence
from engine.history import EditHistory
from engine.executor import build_ffmpeg_command, _tempo_chain
from engine.transcript_loader import _load_srt, _load_json


def test_tempo_chain_extreme_high():
    chain = _tempo_chain(8.0)
    assert len(chain) == 3  # 2.0 * 2.0 * 2.0 = 8.0
    assert chain[0] == "atempo=2.0"
    assert chain[-1] == "atempo=2.0"


def test_tempo_chain_extreme_low():
    chain = _tempo_chain(0.125)
    assert len(chain) == 3  # 0.5 * 0.5 * 0.5 = 0.125
    assert chain[0] == "atempo=0.5"


def test_snap_to_silence_prefer_end():
    t = Transcript(words=[
        TranscriptWord("First", 0.0, 1.0),
        TranscriptWord("Second", 2.0, 3.0),
    ])
    # Gap is 1.0 to 2.0 (midpoint 1.5). For t=1.4 with prefer="end", should snap to 2.0
    snapped = _snap_to_silence(1.4, t, prefer="end")
    assert snapped == 2.0


def test_snap_to_silence_outside_radius():
    t = Transcript(words=[
        TranscriptWord("First", 0.0, 1.0),
        TranscriptWord("Second", 5.0, 6.0),
    ])
    # Gap is 1.0 to 5.0 (midpoint 3.0). For t=1.2, midpoint distance is 1.8 > 0.5, so no snap
    snapped = _snap_to_silence(1.2, t)
    assert snapped == 1.2


def test_parse_combined_hms_and_seconds():
    pi = parse_instruction("Trim from 00:01:30 to 120s")
    assert pi.kind == StepKind.TRIM
    assert pi.t_start == 90.0
    assert pi.t_end == 120.0


def test_parse_overlay_instruction():
    pi = parse_instruction("Add overlay 'logo.png' from 0:10 to 0:20")
    assert pi.kind == StepKind.OVERLAY
    assert pi.params["path"] == "logo.png"
    assert pi.t_start == 10.0
    assert pi.t_end == 20.0


def test_parse_volume_percentage_extreme():
    pi = parse_instruction("Set volume to 200%")
    assert pi.kind == StepKind.VOLUME
    assert pi.params["level_db"] > 5.0


def test_load_srt_malformed_blocks():
    malformed = "1\nInvalid time block\nSome text\n\n2\n00:00:01,000 --> 00:00:03,000\nValid block\n"
    t = _load_srt(malformed)
    assert len(t.words) == 2
    assert t.words[0].word == "Valid"


def test_executor_overlay_and_fades_combined():
    steps = [
        EditStep(kind=StepKind.FADE, params={"direction": "in", "duration": 1.5}),
        EditStep(kind=StepKind.FADE, params={"direction": "out", "duration": 2.0}),
        EditStep(kind=StepKind.VOLUME, params={"level_db": 3.0}),
    ]
    cmd = build_ffmpeg_command(steps, "in.mp4", "out.mp4")
    cmd_str = " ".join(cmd)
    assert "fade=" in cmd_str
    assert "afade=" in cmd_str
    assert "volume=" in cmd_str


def test_history_restore_first_step():
    s = EditSession()
    h = EditHistory(s)
    step1 = EditStep(kind=StepKind.TRIM, anchor_start=0.0, anchor_end=10.0)
    step2 = EditStep(kind=StepKind.CUT, anchor_start=2.0, anchor_end=3.0)
    h.apply(step1)
    h.apply(step2)
    assert h.step_count == 2
    ok = h.restore(step1.id)
    assert ok is True
    assert h.step_count == 1
    assert h.steps[0].id == step1.id


def test_plan_with_case_insensitive_phrases():
    words = [
        TranscriptWord("HELLO", 0.0, 0.8),
        TranscriptWord("WORLD", 1.0, 1.8),
    ]
    s = EditSession()
    s.transcript = Transcript(words=words)
    pi = parse_instruction("Start from 'hello world'")
    step = plan_edit(s, pi, video_duration=10.0)
    assert step.anchor_start == 0.0


def test_step_describe_formatting():
    step_cut = EditStep(kind=StepKind.CUT, anchor_start=1.234, anchor_end=5.678)
    assert "Cut segment [1.23s – 5.68s]" in step_cut.describe()

    step_sub = EditStep(kind=StepKind.SUBTITLE, params={"text": "Hello"})
    assert 'Add subtitle: "Hello"' in step_sub.describe()


def test_multiple_silence_operations():
    steps = [
        EditStep(kind=StepKind.SILENCE, anchor_start=1.0, anchor_end=2.0),
        EditStep(kind=StepKind.SILENCE, anchor_start=4.0, anchor_end=5.0),
    ]
    cmd = build_ffmpeg_command(steps, "test.mp4", "out.mp4")
    cmd_str = " ".join(cmd)
    assert cmd_str.count("volume=0") == 2
