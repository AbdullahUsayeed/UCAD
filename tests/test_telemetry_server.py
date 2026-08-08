"""Tests for telemetry server and database modules."""

import os
import sys
import time
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

# Use a temp file for SQLite to avoid Windows :memory: path issues
_db_path = os.path.join(os.path.dirname(__file__), "_test_telemetry.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_path}"
os.environ["TELEMETRY_API_KEY"] = "test-key"

from sqlalchemy import select

from database import Base, Machine, Session as SessionModel, Event, engine, AsyncSessionLocal
import server as server_mod
from server import app, Payload, TelemetryEvent


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    try:
        os.remove(_db_path)
    except OSError:
        pass


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        headers={"X-Api-Key": "test-key"},
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_receive_events(client):
    payload = {
        "session_id": "sess-001",
        "machine_id": "mach-001",
        "events": [
            {
                "command": "App.newDocument()",
                "timestamp": time.time(),
                "source": "gui_command",
                "workbench": "PartDesign",
            }
        ],
    }
    resp = await client.post("/api/events", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["processed"] == 1


@pytest.mark.asyncio
async def test_receive_empty_events(client):
    payload = {
        "session_id": "sess-002",
        "machine_id": "mach-002",
        "events": [],
    }
    resp = await client.post("/api/events", json=payload)
    assert resp.status_code == 200
    assert resp.json()["processed"] == 0


@pytest.mark.asyncio
async def test_receive_multiple_events_same_batch(client):
    now = time.time()
    payload = {
        "session_id": "sess-003",
        "machine_id": "mach-003",
        "events": [
            {"command": f"cmd_{i}", "timestamp": now + i, "source": "gui_command", "workbench": "Part"}
            for i in range(5)
        ],
    }
    resp = await client.post("/api/events", json=payload)
    assert resp.status_code == 200
    assert resp.json()["processed"] == 5


@pytest.mark.asyncio
async def test_upsert_machine_on_multiple_sessions(client):
    for i in range(3):
        payload = {
            "session_id": f"sess-00{i}",
            "machine_id": "mach-004",
            "events": [
                {"command": f"cmd_{i}", "timestamp": time.time(), "source": "gui_command", "workbench": "Part"}
            ],
        }
        resp = await client.post("/api/events", json=payload)
        assert resp.status_code == 200

    async with AsyncSessionLocal() as db:
        machine = await db.execute(
            select(Machine).where(Machine.machine_id == "mach-004")
        )
        machine = machine.scalar_one()
        assert machine.total_events == 3
        assert machine.total_sessions == 3


@pytest.mark.asyncio
async def test_delete_machine_events(client):
    payload = {
        "session_id": "sess-delete",
        "machine_id": "mach-delete",
        "events": [
            {"command": "delete_me", "timestamp": time.time(), "source": "gui_command", "workbench": "Part"}
        ],
    }
    resp = await client.post("/api/events", json=payload)
    assert resp.status_code == 200

    resp = await client.delete("/api/events/mach-delete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    resp = await client.delete("/api/events/mach-delete")
    assert resp.json()["status"] == "not_found"


@pytest.mark.asyncio
async def test_get_machine_events(client):
    now = time.time()
    payload = {
        "session_id": "sess-get",
        "machine_id": "mach-get",
        "events": [
            {"command": "first", "timestamp": now, "source": "gui_command", "workbench": "Part"},
            {"command": "second", "timestamp": now + 1, "source": "console_input", "workbench": "Part"},
        ],
    }
    resp = await client.post("/api/events", json=payload)
    assert resp.status_code == 200

    resp = await client.get("/api/events/mach-get")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2

    resp = await client.get("/api/events/mach-get?source=console_input")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["command"] == "second"


@pytest.mark.asyncio
async def test_get_stats(client):
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_machines" in data
    assert "total_events" in data
    assert "total_sessions" in data
    assert "events_last_24h" in data


@pytest.mark.asyncio
async def test_pydantic_models():
    event = TelemetryEvent(command="test", timestamp=123.0, source="gui", workbench="Part")
    assert event.freecad_version == ""
    assert event.doc_summary == ""

    payload = Payload(
        session_id="sess",
        machine_id="mach",
        events=[event],
    )
    assert len(payload.events) == 1
    assert payload.model_dump()["session_id"] == "sess"


@pytest.mark.asyncio
async def test_extra_fields_ignored():
    payload = Payload(
        session_id="sess",
        machine_id="mach",
        events=[
            TelemetryEvent(
                command="test", timestamp=1.0, source="gui", workbench="Part",
                extra_field="should_be_ignored",
            )
        ],
    )
    dump = payload.model_dump()
    assert "extra_field" not in dump["events"][0]


@pytest.mark.asyncio
async def test_receive_with_metadata(client):
    payload = {
        "session_id": "sess-meta",
        "machine_id": "mach-meta",
        "events": [
            {
                "command": "App.newDocument()",
                "timestamp": time.time(),
                "source": "ai_script",
                "workbench": "PartDesign",
                "freecad_version": "1.0.0",
                "doc_summary": '{"count": 3, "types": {"Part": 3}}',
            }
        ],
    }
    resp = await client.post("/api/events", json=payload)
    assert resp.status_code == 200

    async with AsyncSessionLocal() as db:
        event = await db.execute(
            select(Event).where(Event.session_id == "sess-meta")
        )
        event = event.scalar_one()
        assert event.freecad_version == "1.0.0"
        assert event.doc_summary == '{"count": 3, "types": {"Part": 3}}'
        assert event.source == "ai_script"


@pytest.mark.asyncio
async def test_rate_limit(client):
    server_mod._requests.clear()
    now = time.time()
    payload = {
        "session_id": "sess-rate",
        "machine_id": "mach-rate",
        "events": [
            {"command": "x", "timestamp": now, "source": "gui_command", "workbench": "Part"}
        ],
    }
    for _ in range(server_mod._RATE_LIMIT_MAX):
        resp = await client.post("/api/events", json=payload)
        assert resp.status_code == 200

    resp = await client.post("/api/events", json=payload)
    assert resp.status_code == 429
