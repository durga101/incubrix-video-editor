"""Core data models for the video editing engine."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class StepKind(str, Enum):
    """Every instruction type the engine understands."""
    TRIM = "trim"
    CUT = "cut"
    SILENCE = "silence"
    SUBTITLE = "subtitle"
    CROP = "crop"
    SPEED = "speed"
    VOLUME = "volume"
    FADE = "fade"
    OVERLAY = "overlay"
    UNDO = "undo"
    RESTORE = "restore"
    UNKNOWN = "unknown"


@dataclass
class TranscriptWord:
    """A single word with timing information from the transcript."""
    word: str
    start: float          # seconds
    end: float            # seconds
    speaker: Optional[str] = None
    confidence: float = 1.0

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Transcript:
    """Full transcript of a video with word-level timing."""
    words: list[TranscriptWord] = field(default_factory=list)
    language: str = "en"
    source: str = "whisper"       # whisper | manual | unknown

    def words_in_range(self, start: float, end: float) -> list[TranscriptWord]:
        """Return all words whose midpoint lies within [start, end]."""
        return [
            w for w in self.words
            if start <= (w.start + w.end) / 2 <= end
        ]

    def find_phrase(self, phrase: str) -> Optional[tuple[float, float]]:
        """
        Locate the first occurrence of a phrase (case-insensitive) and return
        its (start, end) timestamps.  Returns None if not found.
        """
        tokens = phrase.lower().split()
        n = len(tokens)
        for i, w in enumerate(self.words):
            if [x.word.lower().strip(".,!?;:\"'") for x in self.words[i:i+n]] == tokens:
                return self.words[i].start, self.words[i + n - 1].end
        return None

    @property
    def duration(self) -> float:
        if not self.words:
            return 0.0
        return self.words[-1].end


@dataclass
class EditStep:
    """A single resolved editing instruction."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: StepKind = StepKind.UNKNOWN
    params: dict[str, Any] = field(default_factory=dict)
    raw_instruction: str = ""
    # Content anchors resolved at planning time
    anchor_start: Optional[float] = None
    anchor_end: Optional[float] = None
    # Snap policy
    snap_to_silence: bool = True

    def describe(self) -> str:
        """Human-readable one-liner."""
        if self.kind == StepKind.TRIM:
            return (
                f"Trim video to [{self.anchor_start:.2f}s – {self.anchor_end:.2f}s]"
            )
        if self.kind == StepKind.CUT:
            return (
                f"Cut segment [{self.anchor_start:.2f}s – {self.anchor_end:.2f}s]"
            )
        if self.kind == StepKind.SILENCE:
            return (
                f"Mute audio [{self.anchor_start:.2f}s – {self.anchor_end:.2f}s]"
            )
        if self.kind == StepKind.SUBTITLE:
            text = self.params.get("text", "")
            return f"Add subtitle: \"{text}\""
        return f"{self.kind.value}: {self.params}"


class RenderStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class RenderJob:
    """Tracks the state of an async render task."""
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    status: RenderStatus = RenderStatus.QUEUED
    progress: float = 0.0           # 0–1
    output_url: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class EditSession:
    """
    The authoritative state for one editing session.

    history   : ordered list of applied EditStep objects
    video_path: local path to the source video file
    transcript: parsed Transcript (optional — engine degrades gracefully)
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    video_path: Optional[str] = None
    transcript: Optional[Transcript] = None
    history: list[EditStep] = field(default_factory=list)
    render_jobs: list[RenderJob] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Convenience                                                          #
    # ------------------------------------------------------------------ #
    def add_step(self, step: EditStep) -> None:
        self.history.append(step)

    def undo_last(self) -> Optional[EditStep]:
        """Pop and return the last step, or None if history is empty."""
        if self.history:
            return self.history.pop()
        return None

    def restore_to(self, step_id: str) -> bool:
        """
        Truncate history up to (and including) the step with *step_id*.
        Returns True if found, False otherwise.
        """
        for i, s in enumerate(self.history):
            if s.id == step_id:
                self.history = self.history[: i + 1]
                return True
        return False

    @property
    def step_count(self) -> int:
        return len(self.history)
