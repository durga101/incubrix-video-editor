"""
Tests for the FFmpeg command builder (executor).

These tests do NOT require FFmpeg to be installed — they check the command
string structure only (dry-run mode).
"""
import pytest
from engine.executor import build_ffmpeg_command
from engine.models import EditStep, StepKind


def _step(kind, start=0.0, end=10.0, params=None):
    return EditStep(
        kind=kind,
        anchor_start=start,
        anchor_end=end,
        params=params or {},
    )


# ---- Basic structure ----

def test_command_starts_with_ffmpeg():
    cmd = build_ffmpeg_command(
        [_step(StepKind.TRIM, 0.0, 10.0)],
        "input.mp4",
        "output.mp4",
    )
    assert cmd[0] == "ffmpeg"
    assert "input.mp4" in cmd
    assert "output.mp4" in cmd[-1]


def test_command_has_overwrite_flag():
    cmd = build_ffmpeg_command(
        [_step(StepKind.CUT, 5.0, 10.0)],
        "in.mp4",
        "out.mp4",
    )
    assert "-y" in cmd


# ---- TRIM ----

def test_trim_uses_trim_filter():
    cmd = build_ffmpeg_command(
        [_step(StepKind.TRIM, 2.0, 8.0)],
        "in.mp4",
        "out.mp4",
    )
    vf = " ".join(cmd)
    assert "trim" in vf
    assert "atrim" in vf


# ---- CUT ----

def test_cut_uses_select_filter():
    cmd = build_ffmpeg_command(
        [_step(StepKind.CUT, 1.0, 3.0)],
        "in.mp4",
        "out.mp4",
    )
    vf = " ".join(cmd)
    assert "select" in vf
    assert "aselect" in vf


def test_multiple_cuts():
    steps = [
        _step(StepKind.CUT, 0.0, 5.0),
        _step(StepKind.CUT, 10.0, 15.0),
    ]
    cmd = build_ffmpeg_command(steps, "in.mp4", "out.mp4")
    vf = " ".join(cmd)
    assert vf.count("between") >= 2


# ---- SILENCE ----

def test_silence_uses_volume_filter():
    cmd = build_ffmpeg_command(
        [_step(StepKind.SILENCE, 5.0, 10.0)],
        "in.mp4",
        "out.mp4",
    )
    vf = " ".join(cmd)
    assert "volume=0" in vf
    assert "between" in vf


# ---- SUBTITLE ----

def test_subtitle_uses_drawtext():
    s = _step(StepKind.SUBTITLE, 0.0, 5.0, params={"text": "Hello", "font_size": 24})
    cmd = build_ffmpeg_command([s], "in.mp4", "out.mp4")
    vf = " ".join(cmd)
    assert "drawtext" in vf
    assert "Hello" in vf


def test_subtitle_escapes_colon():
    s = _step(StepKind.SUBTITLE, 0.0, 5.0, params={"text": "A:B", "font_size": 24})
    cmd = build_ffmpeg_command([s], "in.mp4", "out.mp4")
    vf = " ".join(cmd)
    assert "\\:" in vf


# ---- SPEED ----

def test_speed_uses_setpts():
    s = _step(StepKind.SPEED, params={"rate": 2.0})
    cmd = build_ffmpeg_command([s], "in.mp4", "out.mp4")
    vf = " ".join(cmd)
    assert "setpts" in vf
    assert "atempo" in vf


def test_speed_high_rate_chains_atempo():
    s = _step(StepKind.SPEED, params={"rate": 4.0})
    cmd = build_ffmpeg_command([s], "in.mp4", "out.mp4")
    vf = " ".join(cmd)
    # 4x requires two atempo=2.0 stages
    assert vf.count("atempo") >= 2


# ---- VOLUME ----

def test_volume_uses_volume_filter():
    s = _step(StepKind.VOLUME, params={"level_db": 6.0})
    cmd = build_ffmpeg_command([s], "in.mp4", "out.mp4")
    vf = " ".join(cmd)
    assert "volume=" in vf


# ---- FADE ----

def test_fade_in_filter():
    s = _step(StepKind.FADE, params={"direction": "in", "duration": 2.0})
    cmd = build_ffmpeg_command([s], "in.mp4", "out.mp4")
    vf = " ".join(cmd)
    assert "fade" in vf
    assert "afade" in vf


# ---- CROP ----

def test_crop_filter():
    s = _step(StepKind.CROP, params={"aspect_w": 16, "aspect_h": 9})
    cmd = build_ffmpeg_command([s], "in.mp4", "out.mp4")
    vf = " ".join(cmd)
    assert "crop" in vf


# ---- Codec flags ----

def test_codec_flags():
    cmd = build_ffmpeg_command(
        [_step(StepKind.TRIM, 0.0, 5.0)],
        "in.mp4",
        "out.mp4",
    )
    assert "-c:v" in cmd
    assert "libx264" in cmd
    assert "-c:a" in cmd
    assert "aac" in cmd


# ---- Empty steps list ----

def test_empty_steps_raises():
    from engine.executor import execute_step
    with pytest.raises(RuntimeError, match="No steps"):
        execute_step([], "in.mp4", "out.mp4", dry_run=True)
