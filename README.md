# Prompt-Based Video Editing Engine

**IncuBrix Software Engineer Assessment — PS2**

A production-quality HTTP API that accepts natural-language editing instructions and applies them to video files using FFmpeg.

---

## Quick Start

### Prerequisites

- Python 3.12+
- [FFmpeg](https://ffmpeg.org/download.html) (Linux: `sudo apt install ffmpeg`; macOS: `brew install ffmpeg`)

```bash
git clone <your-repo-url>
cd incubrix-video-editor

python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements-dev.txt
```

### Run the test suite

```bash
python -m pytest -q
```

Expected: **all tests pass** (≈ 2–3 minutes).

### Run the example sessions (local engine)

```bash
python -m cli.session_runner sessions/ --local --out out/
```

Expected: 5 sessions processed; `out/<name>_result.json` written for each.

### Start the API server

```bash
uvicorn app.main:get_app --factory --port 8000
```

Then open <http://localhost:8000/docs> for the interactive API documentation.

### Docker (optional)

```bash
cp .env.example .env
docker compose up --build
```

API: <http://localhost:8000> · MinIO console: <http://localhost:9001> (minioadmin / minioadmin)

---

## Project Layout

```
.
├── app/                        # FastAPI application
│   ├── main.py                 # App factory
│   ├── store.py                # In-memory session store
│   └── routers/
│       ├── health.py           # GET /health
│       ├── sessions.py         # Session CRUD + edit endpoint
│       └── render.py           # Async render + polling
├── cli/
│   └── session_runner.py       # Batch session runner (local or API)
├── engine/                     # Core editing logic
│   ├── models.py               # Data models (EditSession, EditStep, …)
│   ├── parser.py               # Natural-language → ParsedInstruction
│   ├── planner.py              # ParsedInstruction → EditStep (anchors)
│   ├── executor.py             # EditStep list → FFmpeg command
│   ├── history.py              # Undo / restore semantics
│   └── transcript_loader.py   # JSON / SRT / VTT loader
├── tests/                      # pytest test suite
│   ├── test_parser.py
│   ├── test_planner.py
│   ├── test_history.py
│   ├── test_render.py          # FFmpeg command builder
│   ├── test_transcript.py
│   ├── test_api.py             # API integration tests
│   ├── test_scale.py
│   └── scenario_data.py        # Shared fixtures
├── sessions/                   # Example session YAML files
├── samples/
│   ├── media/                  # Sample video files (place here)
│   └── transcripts/            # Sample transcript JSON files
├── tools/
│   └── measure_metrics.py      # Metric measurement script
├── docs/
│   ├── WALKTHROUGH.md
│   └── DEPLOY.md
├── openapi.yaml                # OpenAPI 3.1 spec
├── REPORT.md
├── SOURCES.md
├── AI_USE.md
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## API Reference

Full spec: [`openapi.yaml`](openapi.yaml) · Interactive docs: `/docs`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/sessions` | Create a new edit session |
| `GET` | `/sessions/{id}` | Get session state |
| `POST` | `/sessions/{id}/upload` | Upload video + transcript |
| `POST` | `/sessions/{id}/edit` | Apply a natural-language instruction |
| `GET` | `/sessions/{id}/history` | List all edit steps |
| `DELETE` | `/sessions/{id}` | Delete a session |
| `POST` | `/render/{id}` | Start an async render job |
| `GET` | `/render/{id}/{job_id}` | Poll render status |

### Example edit request

```bash
curl -X POST http://localhost:8000/sessions/{SESSION_ID}/edit \
  -H "Content-Type: application/json" \
  -d '{"instruction": "Remove everything before \"Good morning everyone\""}'
```

Response includes three answers:
- **answer_a**: what the engine will do
- **answer_b**: limitations or warnings
- **answer_c**: suggested next instruction

---

## Supported Instructions

| Instruction type | Example |
|-----------------|---------|
| Trim (keep range) | `"Keep from 0:30 to 1:45"` |
| Cut (remove range) | `"Cut from 1:00 to 2:00"` |
| Phrase anchor trim | `"Remove everything before 'Welcome back'"` |
| Phrase anchor cut | `"Cut between 'uh' and 'anyway'"` |
| Mute / silence | `"Mute audio from 0:30 to 0:45"` |
| Subtitle | `"Add subtitle 'Chapter 1' at 0:10"` |
| Speed change | `"Speed up 2x"` / `"Slow down to 0.5x"` |
| Volume | `"Make the audio louder"` / `"Set volume to 50%"` |
| Fade | `"Fade in over 2 seconds"` |
| Crop | `"Crop to 16:9"` |
| Undo | `"Undo"` / `"Revert"` |
| Restore | `"Restore to step '<id>'"` |

---

## Architecture Overview

```
User prompt
    │
    ▼
parser.parse_instruction()   ← NLP pattern matching
    │  ParsedInstruction
    ▼
planner.plan_edit()          ← Resolve phrases → timestamps
    │  EditStep (anchors resolved)    ← Snap to silence gaps
    ▼
history.EditHistory.apply()  ← Append / undo / restore
    │  list[EditStep]
    ▼
executor.build_ffmpeg_command()  ← FFmpeg filter graph builder
    │  subprocess call
    ▼
render output (.mp4)
```

Key design choices:
- **Content-anchored edits**: phrases are looked up in the transcript; cuts snap to the nearest silence gap (within ±0.5 s).
- **History replay**: the FFmpeg command is rebuilt from scratch on every render, so undo/restore is always consistent.
- **Three-answer format**: every `/edit` response includes what will happen, what cannot be done, and a suggested next step.

---

## Development

```bash
# Run all tests with coverage
python -m pytest --cov=engine --cov=app -q

# Type check
mypy engine/ app/ --ignore-missing-imports

# Format
black engine/ app/ tests/ cli/ tools/
isort engine/ app/ tests/ cli/ tools/
```

---

## Licence

MIT — see `SOURCES.md` for third-party licences.
