"""
Scenario data: test fixtures and helpers for integration tests.

These are used by the session runner and can also be imported by
individual test modules.
"""
from __future__ import annotations

from engine.models import EditSession, Transcript, TranscriptWord


def make_interview_transcript() -> Transcript:
    """
    A synthetic interview transcript simulating a 90-second video.

    Contains:
    - Opening greeting
    - A filler word ("uh") with surrounding silence
    - Main content
    - Closing words
    """
    return Transcript(
        words=[
            TranscriptWord("Good", 0.1, 0.4),
            TranscriptWord("morning", 0.5, 0.9),
            TranscriptWord("everyone", 1.0, 1.4),
            TranscriptWord("and", 1.5, 1.6),
            TranscriptWord("welcome", 1.7, 2.1),
            TranscriptWord("to", 2.2, 2.3),
            TranscriptWord("our", 2.4, 2.6),
            TranscriptWord("show", 2.7, 3.0),
            # silence 3.0 – 4.0
            TranscriptWord("uh", 4.1, 4.3),
            # silence 4.3 – 5.0
            TranscriptWord("today", 5.1, 5.5),
            TranscriptWord("we", 5.6, 5.8),
            TranscriptWord("are", 5.9, 6.1),
            TranscriptWord("discussing", 6.2, 6.8),
            TranscriptWord("video", 6.9, 7.2),
            TranscriptWord("editing", 7.3, 7.7),
            # silence 7.7 – 9.0
            TranscriptWord("Let", 9.1, 9.3),
            TranscriptWord("us", 9.4, 9.5),
            TranscriptWord("get", 9.6, 9.8),
            TranscriptWord("started", 9.9, 10.3),
            # silence 10.3 – 20.0  (long section — simulating content)
            TranscriptWord("That", 20.1, 20.4),
            TranscriptWord("is", 20.5, 20.6),
            TranscriptWord("all", 20.7, 20.9),
            TranscriptWord("for", 21.0, 21.1),
            TranscriptWord("today", 21.2, 21.6),
            TranscriptWord("goodbye", 22.0, 22.5),
        ],
        language="en",
        source="synthetic",
    )


def make_session_with_transcript() -> EditSession:
    s = EditSession()
    s.transcript = make_interview_transcript()
    s.metadata["video_duration"] = 90.0
    return s
