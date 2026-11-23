"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import sessions, render, health


def get_app() -> FastAPI:
    """
    Application factory used by uvicorn:

        uvicorn app.main:get_app --factory --port 8000
    """
    app = FastAPI(
        title="Prompt-Based Video Editing Engine",
        description=(
            "IncuBrix PS2 — an HTTP API that accepts natural-language "
            "editing instructions and applies them to video files using FFmpeg."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
    app.include_router(render.router, prefix="/render", tags=["render"])

    return app
