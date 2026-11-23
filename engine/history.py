"""
Edit history management.

Provides undo (pop the last step) and restore (truncate to a checkpoint)
semantics, plus serialization helpers.
"""
from __future__ import annotations

import json
from typing import Optional

from .models import EditSession, EditStep, StepKind


class EditHistory:
    """
    Wraps an EditSession and exposes history operations.

    Design note
    -----------
    *Undo* removes only the **last** step (undo-stack behaviour).
    *Restore* truncates the history to a named step and re-applies
    everything up to that point.  This is different from "undo N times"
    because it lets the user jump to any named checkpoint without
    discarding intermediate steps that come before it.
    """

    def __init__(self, session: EditSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    # Mutation                                                             #
    # ------------------------------------------------------------------ #

    def apply(self, step: EditStep) -> None:
        """Append a step to the history (after planning)."""
        if step.kind == StepKind.UNDO:
            self.undo()
        elif step.kind == StepKind.RESTORE:
            step_id = step.params.get("step_id")
            if step_id:
                ok = self.restore(step_id)
                if not ok:
                    raise ValueError(f"Step ID not found in history: {step_id!r}")
            else:
                raise ValueError("RESTORE requires a step_id parameter")
        else:
            self._session.add_step(step)

    def undo(self) -> Optional[EditStep]:
        """Remove and return the most-recently applied step."""
        return self._session.undo_last()

    def restore(self, step_id: str) -> bool:
        """Truncate history to the step identified by *step_id*."""
        return self._session.restore_to(step_id)

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    @property
    def steps(self) -> list[EditStep]:
        return list(self._session.history)

    def as_dict(self) -> list[dict]:
        """Serialise history to a JSON-safe list."""
        result = []
        for s in self._session.history:
            result.append(
                {
                    "id": s.id,
                    "kind": s.kind.value,
                    "params": s.params,
                    "raw_instruction": s.raw_instruction,
                    "anchor_start": s.anchor_start,
                    "anchor_end": s.anchor_end,
                }
            )
        return result

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2)

    @property
    def step_count(self) -> int:
        return self._session.step_count
