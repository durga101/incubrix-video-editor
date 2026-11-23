"""Health-check router."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return 200 OK when the service is running."""
    return HealthResponse(status="ok", version="1.0.0")
