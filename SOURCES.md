# SOURCES.md — Third-Party Libraries and Assets

## Runtime Dependencies

| Package | Version | Licence | Use |
|---------|---------|---------|-----|
| FastAPI | ≥ 0.111 | MIT | HTTP framework |
| Uvicorn | ≥ 0.29 | BSD-3 | ASGI server |
| Pydantic | ≥ 2.7 | MIT | Data validation |
| python-multipart | ≥ 0.0.9 | Apache 2.0 | File upload parsing |
| httpx | ≥ 0.27 | BSD-3 | HTTP client (session runner + tests) |
| PyYAML | ≥ 6.0 | MIT | Session YAML files |

## Development Dependencies

| Package | Version | Licence | Use |
|---------|---------|---------|-----|
| pytest | ≥ 8.1 | MIT | Test runner |
| pytest-asyncio | ≥ 0.23 | Apache 2.0 | Async test support |
| pytest-cov | ≥ 5.0 | MIT | Coverage reporting |
| black | ≥ 24.0 | MIT | Code formatting |
| isort | ≥ 5.13 | MIT | Import sorting |
| mypy | ≥ 1.9 | MIT | Type checking |
| ruff | ≥ 0.4 | MIT | Linting |

## System Dependencies

| Software | Licence | Use |
|----------|---------|-----|
| FFmpeg | LGPL 2.1+ / GPL 2+ | Video encoding and filter graph |
| fonts-dejavu-core | Bitstream Vera / DejaVu | Subtitle rendering font |

> FFmpeg is linked dynamically and not bundled in this repository.

## Docker Base Image

| Image | Licence | Notes |
|-------|---------|-------|
| python:3.12-slim | PSF / Debian | Official Python image |
| minio/minio | AGPL 3.0 | Object storage (dev only) |

## AI Tools Used

See `AI_USE.md` for full disclosure of AI coding assistant usage.

## Sample Media

The `samples/` directory does **not** include actual video files (they are git-ignored).
The transcript file `samples/transcripts/interview_single.transcript.json` is **synthetic**,
created by the development team, and contains no real speech or personal data.

All assets used in the solution are either:
- Generated/synthetic (transcripts, test fixtures)
- Provided by the user at runtime (video files)

No third-party copyrighted media is bundled.
