"""
Render router.

POST /render/{session_id}        — Start an async render job
GET  /render/{session_id}/{job_id} — Poll job status
"""
from __future__ import annotations

import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.store import get_session
from engine.executor import build_ffmpeg_command, run_ffmpeg
from engine.models import RenderJob, RenderStatus, StepKind

router = APIRouter()

# ---- job store (in-memory for assessment; would be Redis/DB in prod) ----
_jobs: dict[str, RenderJob] = {}
_lock = threading.Lock()


class RenderRequest(BaseModel):
    output_format: str = "mp4"


class RenderStatusResponse(BaseModel):
    job_id: str
    session_id: str
    status: str
    progress: float
    output_url: Optional[str] = None
    error: Optional[str] = None


@router.post("/{session_id}", response_model=RenderStatusResponse, status_code=202)
async def start_render(
    session_id: str,
    body: RenderRequest,
    background_tasks: BackgroundTasks,
) -> RenderStatusResponse:
    """
    Enqueue a render job.  Returns immediately with job_id; poll for status.
    """
    session = _get_session_or_404(session_id)

    if not session.video_path or not Path(session.video_path).exists():
        raise HTTPException(
            status_code=422,
            detail="No video uploaded for this session.",
        )

    active_steps = [
        s for s in session.history
        if s.kind not in (StepKind.UNDO, StepKind.RESTORE, StepKind.UNKNOWN)
    ]
    if not active_steps:
        raise HTTPException(
            status_code=422,
            detail="No edit steps to render.",
        )

    job = RenderJob(
        session_id=session_id,
        status=RenderStatus.QUEUED,
        created_at=_now(),
        updated_at=_now(),
    )
    with _lock:
        _jobs[job.job_id] = job
    session.render_jobs.append(job)

    background_tasks.add_task(
        _run_render,
        job_id=job.job_id,
        steps=list(active_steps),
        input_path=session.video_path,
        output_format=body.output_format,
    )

    return RenderStatusResponse(
        job_id=job.job_id,
        session_id=session_id,
        status=job.status.value,
        progress=0.0,
    )


@router.get("/{session_id}/{job_id}", response_model=RenderStatusResponse)
async def poll_render(session_id: str, job_id: str) -> RenderStatusResponse:
    """Return the current status of a render job."""
    with _lock:
        job = _jobs.get(job_id)

    if job is None or job.session_id != session_id:
        raise HTTPException(status_code=404, detail="Render job not found")

    return RenderStatusResponse(
        job_id=job.job_id,
        session_id=session_id,
        status=job.status.value,
        progress=job.progress,
        output_url=job.output_url,
        error=job.error,
    )


# ------------------------------------------------------------------ #
# Background task                                                     #
# ------------------------------------------------------------------ #

def _run_render(
    job_id: str,
    steps: list,
    input_path: str,
    output_format: str = "mp4",
) -> None:
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        return

    _update_job(job, status=RenderStatus.PROCESSING, progress=0.1)

    out_dir = Path(tempfile.mkdtemp(prefix="incubrix_render_"))
    output_path = str(out_dir / f"output.{output_format}")

    try:
        cmd = build_ffmpeg_command(steps, input_path, output_path)
        _update_job(job, progress=0.5)
        run_ffmpeg(cmd)
        _update_job(
            job,
            status=RenderStatus.DONE,
            progress=1.0,
            output_url=f"/files/{Path(output_path).name}",
        )
        # Store output path in job for file serving (simple impl)
        with _lock:
            job.output_url = output_path  # absolute for now
    except Exception as exc:
        _update_job(job, status=RenderStatus.FAILED, error=str(exc))


def _update_job(job: RenderJob, **kwargs) -> None:
    with _lock:
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at = _now()


def _get_session_or_404(session_id: str):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
