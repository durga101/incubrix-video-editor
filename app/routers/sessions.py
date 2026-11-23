"""
Sessions router.

Endpoints
---------
POST   /sessions                     — Create a new session
GET    /sessions/{session_id}        — Get session state + history
POST   /sessions/{session_id}/upload — Upload video + transcript
POST   /sessions/{session_id}/edit   — Apply a natural-language instruction
GET    /sessions/{session_id}/history — Full history list
DELETE /sessions/{session_id}        — Delete session
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.store import create_session, delete_session, get_session
from engine.executor import execute_step
from engine.history import EditHistory
from engine.models import StepKind
from engine.parser import parse_instruction
from engine.planner import plan_edit
from engine.transcript_loader import load_transcript

router = APIRouter()


# ------------------------------------------------------------------ #
# Schema                                                              #
# ------------------------------------------------------------------ #

class SessionResponse(BaseModel):
    session_id: str
    step_count: int
    video_path: Optional[str] = None
    has_transcript: bool = False


class EditRequest(BaseModel):
    instruction: str
    dry_run: bool = False


class EditResponse(BaseModel):
    session_id: str
    step_id: str
    kind: str
    description: str
    anchor_start: Optional[float] = None
    anchor_end: Optional[float] = None
    ffmpeg_command: Optional[str] = None
    answer_a: str = ""   # what the engine will do
    answer_b: str = ""   # what it cannot do / warnings
    answer_c: str = ""   # suggested next instruction


class HistoryItem(BaseModel):
    id: str
    kind: str
    raw_instruction: str
    anchor_start: Optional[float]
    anchor_end: Optional[float]
    description: str


class HistoryResponse(BaseModel):
    session_id: str
    steps: list[HistoryItem]


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@router.post("", response_model=SessionResponse, status_code=201)
async def create_new_session() -> SessionResponse:
    """Create a fresh edit session."""
    session = create_session()
    return SessionResponse(
        session_id=session.session_id,
        step_count=0,
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_state(session_id: str) -> SessionResponse:
    session = _get_or_404(session_id)
    return SessionResponse(
        session_id=session.session_id,
        step_count=session.step_count,
        video_path=session.video_path,
        has_transcript=session.transcript is not None,
    )


@router.post("/{session_id}/upload")
async def upload_media(
    session_id: str,
    video: UploadFile = File(...),
    transcript: Optional[UploadFile] = File(None),
) -> dict:
    """Upload a video file and optional transcript to an existing session."""
    session = _get_or_404(session_id)

    # Save video to a temp location
    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    tmp_dir = Path(tempfile.mkdtemp(prefix="incubrix_"))
    video_path = tmp_dir / f"source{suffix}"
    with open(video_path, "wb") as f:
        f.write(await video.read())

    session.video_path = str(video_path)

    # Optionally load transcript
    if transcript is not None:
        t_suffix = Path(transcript.filename or "t.json").suffix or ".json"
        t_path = tmp_dir / f"transcript{t_suffix}"
        with open(t_path, "wb") as f:
            f.write(await transcript.read())
        try:
            session.transcript = load_transcript(t_path)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Could not parse transcript: {exc}",
            )

    return {
        "session_id": session_id,
        "video_path": str(video_path),
        "has_transcript": session.transcript is not None,
        "word_count": len(session.transcript.words) if session.transcript else 0,
    }


@router.post("/{session_id}/edit", response_model=EditResponse)
async def apply_edit(session_id: str, body: EditRequest) -> EditResponse:
    """
    Parse and apply a natural-language editing instruction.

    Three-answer format
    -------------------
    answer_a : what the engine understood and will do
    answer_b : limitations, warnings, or what it cannot do
    answer_c : suggested follow-up instruction
    """
    session = _get_or_404(session_id)

    instruction = body.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=422, detail="Instruction cannot be empty")

    # 1. Parse
    try:
        pi = parse_instruction(instruction)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Parse error: {exc}")

    if pi.kind == StepKind.UNKNOWN:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not understand the instruction. "
                "Try being more specific, e.g. 'Cut from 0:30 to 1:00'."
            ),
        )

    # 2. Plan
    video_duration: Optional[float] = session.metadata.get("video_duration")
    try:
        step = plan_edit(session, pi, video_duration=video_duration)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 3. Build history / handle undo-restore
    history = EditHistory(session)
    try:
        history.apply(step)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 4. Optionally execute (dry-run always; full execution if video exists)
    ffmpeg_command: Optional[str] = None
    if body.dry_run or not session.video_path:
        from engine.executor import build_ffmpeg_command
        cmd = build_ffmpeg_command(
            [s for s in session.history if s.kind not in (StepKind.UNDO, StepKind.RESTORE)],
            session.video_path or "input.mp4",
            "output.mp4",
        )
        ffmpeg_command = " ".join(cmd)

    # 5. Build three-answer response
    description = step.describe()
    answer_a = _build_answer_a(step)
    answer_b = _build_answer_b(step, session)
    answer_c = _build_answer_c(step)

    return EditResponse(
        session_id=session_id,
        step_id=step.id,
        kind=step.kind.value,
        description=description,
        anchor_start=step.anchor_start,
        anchor_end=step.anchor_end,
        ffmpeg_command=ffmpeg_command,
        answer_a=answer_a,
        answer_b=answer_b,
        answer_c=answer_c,
    )


@router.get("/{session_id}/history", response_model=HistoryResponse)
async def get_history(session_id: str) -> HistoryResponse:
    session = _get_or_404(session_id)
    items = [
        HistoryItem(
            id=s.id,
            kind=s.kind.value,
            raw_instruction=s.raw_instruction,
            anchor_start=s.anchor_start,
            anchor_end=s.anchor_end,
            description=s.describe(),
        )
        for s in session.history
    ]
    return HistoryResponse(session_id=session_id, steps=items)


@router.delete("/{session_id}", status_code=204)
async def delete_session_endpoint(session_id: str) -> None:
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")


# ------------------------------------------------------------------ #
# Private helpers                                                      #
# ------------------------------------------------------------------ #

def _get_or_404(session_id: str):
    from app.store import get_session as gs
    session = gs(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _build_answer_a(step) -> str:
    if step.kind == StepKind.TRIM:
        return (
            f"I will keep only the video segment from "
            f"{step.anchor_start:.2f}s to {step.anchor_end:.2f}s, "
            f"removing everything outside this range."
        )
    if step.kind == StepKind.CUT:
        return (
            f"I will remove the segment from "
            f"{step.anchor_start:.2f}s to {step.anchor_end:.2f}s, "
            f"joining the remaining parts seamlessly."
        )
    if step.kind == StepKind.SILENCE:
        return (
            f"I will mute the audio between "
            f"{step.anchor_start:.2f}s and {step.anchor_end:.2f}s. "
            f"The video will remain unchanged."
        )
    if step.kind == StepKind.SUBTITLE:
        text = step.params.get("text", "")
        return (
            f"I will add the subtitle \"{text}\" from "
            f"{step.anchor_start:.2f}s to {step.anchor_end:.2f}s "
            f"using white text centered near the bottom."
        )
    if step.kind == StepKind.UNDO:
        return "I will undo the last editing step."
    if step.kind == StepKind.RESTORE:
        return f"I will restore the history to step {step.params.get('step_id', '?')}."
    return f"I will apply a {step.kind.value} operation."


def _build_answer_b(step, session) -> str:
    warnings = []
    if session.video_path is None:
        warnings.append("No video has been uploaded yet; this change is queued but cannot render.")
    if session.transcript is None and step.kind in (StepKind.CUT, StepKind.TRIM, StepKind.SILENCE):
        warnings.append(
            "No transcript was provided; content-anchored edits use timestamps directly. "
            "Silence-snap is disabled."
        )
    if not warnings:
        return "No limitations for this operation."
    return " ".join(warnings)


def _build_answer_c(step) -> str:
    suggestions = {
        StepKind.TRIM: "You can now add subtitles, adjust volume, or render the result.",
        StepKind.CUT: "You can cut another section, add a subtitle, or render the result.",
        StepKind.SILENCE: "You can mute another section or render the result.",
        StepKind.SUBTITLE: "You can add more subtitles, trim the video, or render the result.",
        StepKind.VOLUME: "You can apply more volume changes or render the result.",
        StepKind.SPEED: "You can further adjust speed or render the result.",
        StepKind.FADE: "You can add another fade or render the result.",
        StepKind.UNDO: "The last step has been undone. You can continue editing or render.",
        StepKind.RESTORE: "History restored. You can continue editing from this point.",
    }
    return suggestions.get(step.kind, "You can continue editing or render the result.")
