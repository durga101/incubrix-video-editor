"""
Integration-style tests for the FastAPI application.

Uses Starlette's TestClient — no server needed.
"""
import pytest
from starlette.testclient import TestClient


@pytest.fixture(scope="module")
def app():
    from app.main import get_app
    return get_app()


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


# ---- health ----

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---- session lifecycle ----

def test_create_session(client):
    r = client.post("/sessions")
    assert r.status_code == 201
    data = r.json()
    assert "session_id" in data
    assert data["step_count"] == 0


def test_get_session(client):
    r = client.post("/sessions")
    sid = r.json()["session_id"]
    r2 = client.get(f"/sessions/{sid}")
    assert r2.status_code == 200
    assert r2.json()["session_id"] == sid


def test_get_nonexistent_session(client):
    r = client.get("/sessions/does-not-exist")
    assert r.status_code == 404


def test_delete_session(client):
    r = client.post("/sessions")
    sid = r.json()["session_id"]
    r2 = client.delete(f"/sessions/{sid}")
    assert r2.status_code == 204
    r3 = client.get(f"/sessions/{sid}")
    assert r3.status_code == 404


# ---- edit instructions ----

def test_edit_trim(client):
    sid = client.post("/sessions").json()["session_id"]
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Keep from 0:10 to 1:00", "dry_run": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "trim"
    assert body["anchor_start"] is not None


def test_edit_cut(client):
    sid = client.post("/sessions").json()["session_id"]
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Cut from 0:30 to 1:00", "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "cut"


def test_edit_silence(client):
    sid = client.post("/sessions").json()["session_id"]
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Mute from 0:05 to 0:10", "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "silence"


def test_edit_subtitle(client):
    sid = client.post("/sessions").json()["session_id"]
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Add subtitle 'Hello World' at 0:05", "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "subtitle"


def test_edit_speed(client):
    sid = client.post("/sessions").json()["session_id"]
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Speed up 2x", "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "speed"


def test_edit_volume(client):
    sid = client.post("/sessions").json()["session_id"]
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Make the audio louder", "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "volume"


def test_edit_undo(client):
    sid = client.post("/sessions").json()["session_id"]
    # Apply a step first
    client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Cut from 0:30 to 1:00", "dry_run": True},
    )
    # Then undo
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Undo", "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "undo"


def test_edit_empty_instruction(client):
    sid = client.post("/sessions").json()["session_id"]
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "", "dry_run": True},
    )
    assert r.status_code == 422


def test_edit_three_answers(client):
    sid = client.post("/sessions").json()["session_id"]
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Trim from 0:10 to 0:30", "dry_run": True},
    )
    body = r.json()
    assert "answer_a" in body
    assert "answer_b" in body
    assert "answer_c" in body
    assert len(body["answer_a"]) > 0


# ---- history ----

def test_history_accumulates(client):
    sid = client.post("/sessions").json()["session_id"]
    for instruction in [
        "Cut from 0:30 to 1:00",
        "Add subtitle 'Part 1' at 0:05",
        "Mute from 0:10 to 0:15",
    ]:
        client.post(
            f"/sessions/{sid}/edit",
            json={"instruction": instruction, "dry_run": True},
        )
    r = client.get(f"/sessions/{sid}/history")
    assert r.status_code == 200
    assert len(r.json()["steps"]) == 3


def test_undo_reduces_history(client):
    sid = client.post("/sessions").json()["session_id"]
    client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Cut from 0:30 to 1:00", "dry_run": True},
    )
    client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Undo", "dry_run": True},
    )
    r = client.get(f"/sessions/{sid}/history")
    assert len(r.json()["steps"]) == 0


# ---- ffmpeg command in response ----

def test_dry_run_returns_ffmpeg_command(client):
    sid = client.post("/sessions").json()["session_id"]
    r = client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Trim from 0:10 to 1:00", "dry_run": True},
    )
    assert "ffmpeg" in (r.json().get("ffmpeg_command") or "")


# ---- render (no video — should 422) ----

def test_render_without_video_422(client):
    sid = client.post("/sessions").json()["session_id"]
    # Add a step first
    client.post(
        f"/sessions/{sid}/edit",
        json={"instruction": "Cut from 0:30 to 1:00", "dry_run": True},
    )
    r = client.post(
        f"/sessions/{sid}/render",
        json={"output_format": "mp4"},
    )
    assert r.status_code in (404, 422)
