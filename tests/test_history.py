"""Tests for edit history (undo / restore)."""
import pytest
from engine.history import EditHistory
from engine.models import EditSession, EditStep, StepKind


def _step(kind=StepKind.CUT, start=0.0, end=5.0) -> EditStep:
    return EditStep(kind=kind, anchor_start=start, anchor_end=end)


def _session_with_steps(n: int) -> tuple[EditSession, EditHistory]:
    s = EditSession()
    h = EditHistory(s)
    for i in range(n):
        h.apply(_step(start=float(i), end=float(i + 1)))
    return s, h


# ---- apply ----

def test_apply_adds_step():
    s = EditSession()
    h = EditHistory(s)
    h.apply(_step())
    assert h.step_count == 1


def test_apply_multiple():
    _, h = _session_with_steps(5)
    assert h.step_count == 5


# ---- undo ----

def test_undo_removes_last():
    s, h = _session_with_steps(3)
    h.undo()
    assert h.step_count == 2


def test_undo_empty_returns_none():
    s = EditSession()
    h = EditHistory(s)
    result = h.undo()
    assert result is None


def test_undo_via_apply():
    s, h = _session_with_steps(3)
    h.apply(EditStep(kind=StepKind.UNDO))
    assert h.step_count == 2


# ---- restore ----

def test_restore_to_step_id():
    s, h = _session_with_steps(5)
    target_id = h.steps[2].id  # third step (index 2)
    h.restore(target_id)
    assert h.step_count == 3
    assert h.steps[-1].id == target_id


def test_restore_missing_id_returns_false():
    _, h = _session_with_steps(3)
    result = h.restore("nonexistent-id")
    assert result is False
    assert h.step_count == 3  # unchanged


def test_restore_via_apply():
    s, h = _session_with_steps(5)
    target_id = h.steps[1].id
    restore_step = EditStep(
        kind=StepKind.RESTORE,
        params={"step_id": target_id},
    )
    h.apply(restore_step)
    assert h.step_count == 2


def test_restore_bad_id_via_apply_raises():
    _, h = _session_with_steps(3)
    with pytest.raises(ValueError, match="not found in history"):
        h.apply(EditStep(kind=StepKind.RESTORE, params={"step_id": "bad"}))


# ---- serialization ----

def test_as_dict():
    _, h = _session_with_steps(2)
    d = h.as_dict()
    assert len(d) == 2
    assert "id" in d[0]
    assert "kind" in d[0]


def test_to_json():
    import json
    _, h = _session_with_steps(2)
    j = json.loads(h.to_json())
    assert len(j) == 2
