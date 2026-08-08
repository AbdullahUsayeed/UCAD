"""
server.py — Telemetry receiver with PostgreSQL backend (FastAPI).

Run locally for testing:
    pip install fastapi uvicorn pydantic sqlalchemy asyncpg
    set DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/telemetry
    set TELEMETRY_API_KEY=your-secret
    python server.py

Production (recommended):
    - Run with gunicorn + uvicorn workers behind nginx (see deploy/).
    - Set DATABASE_URL and TELEMETRY_API_KEY in /etc/telemetry/env.
    - Terminate TLS at nginx (get a domain first so clients trust the cert).
"""

import os
import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    init_db,
    AsyncSessionLocal,
    engine,
    Machine,
    Session as SessionModel,
    Event,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("telemetry")

_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 300
_API_KEY = os.getenv("TELEMETRY_API_KEY", "")
_requests: dict = {}


def _client_ip(request: Request) -> str:
    """Use the real client IP passed by nginx (X-Forwarded-For)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _authorized(request: Request) -> bool:
    # Fail closed: if no API key is configured, deny all ingest requests
    # rather than silently exposing the endpoint to the public.
    if not _API_KEY:
        return False
    got = request.headers.get("x-api-key") or request.headers.get("authorization") or ""
    if got.startswith("Bearer "):
        got = got[7:].strip()
    return got == _API_KEY


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not _API_KEY:
        logger.warning("TELEMETRY_API_KEY is NOT set — ingest endpoint is OPEN to the public.")
    await init_db()
    logger.info("Telemetry service started.")
    yield


app = FastAPI(title="Telemetry Receiver", version="2.1.0", lifespan=lifespan)


class TelemetryEvent(BaseModel):
    command: str
    timestamp: float
    source: str
    workbench: str
    freecad_version: Optional[str] = ""
    doc_summary: Optional[str] = ""
    prompt: Optional[str] = ""
    success: Optional[bool] = None
    result: Optional[str] = ""

    model_config = {"extra": "ignore"}


class Payload(BaseModel):
    events: List[TelemetryEvent]
    session_id: str
    machine_id: str

    model_config = {"extra": "ignore"}


class StatsResponse(BaseModel):
    total_machines: int
    total_sessions: int
    total_events: int
    events_last_24h: int
    db_size_mb: float


@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    # /health stays open so clients can probe reachability during startup.
    if request.url.path != "/health":
        if not _authorized(request):
            return JSONResponse(
                status_code=401,
                content={"detail": "unauthorized — missing/invalid API key"},
            )
        ip = _client_ip(request)
        now = time.time()
        window = _requests.get(ip, [])
        window = [t for t in window if t > now - _RATE_LIMIT_WINDOW]
        if len(window) >= _RATE_LIMIT_MAX:
            return JSONResponse(status_code=429, content={"status": "rate_limited"})
        window.append(now)
        _requests[ip] = window
    return await call_next(request)

async def _upsert_machine(db: AsyncSession, machine_id: str):
    result = await db.execute(select(Machine).where(Machine.machine_id == machine_id))
    machine = result.scalar_one_or_none()
    if machine:
        machine.last_seen = datetime.now(timezone.utc)
    else:
        machine = Machine(
            machine_id=machine_id,
            total_events=0,
            total_sessions=0,
        )
        db.add(machine)
    return machine


@app.post("/api/events")
async def receive_events(
    payload: Payload,
):
    if not payload.events:
        return {"status": "success", "processed": 0}

    async with AsyncSessionLocal() as db:
        try:
            machine = await _upsert_machine(db, payload.machine_id)

            session = await db.execute(
                select(SessionModel).where(
                    SessionModel.session_id == payload.session_id
                )
            )
            session = session.scalar_one_or_none()
            if not session:
                session = SessionModel(
                    session_id=payload.session_id,
                    machine_id=payload.machine_id,
                )
                db.add(session)
                machine.total_sessions = (machine.total_sessions or 0) + 1

            event_records = []
            for ev in payload.events:
                event_records.append(Event(
                    session_id=payload.session_id,
                    machine_id=payload.machine_id,
                    timestamp=ev.timestamp,
                    source=ev.source,
                    workbench=ev.workbench,
                    command=ev.command,
                    freecad_version=ev.freecad_version or None,
                    doc_summary=ev.doc_summary or None,
                    prompt=ev.prompt or None,
                    success=ev.success if ev.success is not None else None,
                    result=ev.result or None,
                ))

            db.add_all(event_records)
            machine.total_events = (machine.total_events or 0) + len(event_records)
            session.event_count = (session.event_count or 0) + len(event_records)
            machine.last_seen = datetime.now(timezone.utc)

            await db.commit()

            logger.info("Received %s events from machine %s (session %s)",
                        len(event_records), payload.machine_id, payload.session_id)
            return {"status": "success", "processed": len(event_records)}

        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/events/{machine_id}")
async def delete_events(machine_id: str):
    async with AsyncSessionLocal() as db:
        try:
            machine = await db.execute(
                select(Machine).where(Machine.machine_id == machine_id)
            )
            machine = machine.scalar_one_or_none()
            if not machine:
                return {"status": "not_found", "machine_id": machine_id}

            await db.delete(machine)
            await db.commit()
            return {"status": "deleted", "machine_id": machine_id}
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events/{machine_id}")
async def get_machine_events(
    machine_id: str,
    limit: int = 100,
    offset: int = 0,
    source: Optional[str] = None,
):
    async with AsyncSessionLocal() as db:
        try:
            query = (
                select(Event)
                .where(Event.machine_id == machine_id)
                .order_by(Event.timestamp.desc())
                .offset(offset)
                .limit(limit)
            )
            if source:
                query = query.where(Event.source == source)

            result = await db.execute(query)
            events = result.scalars().all()

            return [
                {
                    "id": e.id,
                    "session_id": e.session_id,
                    "timestamp": e.timestamp,
                    "source": e.source,
                    "workbench": e.workbench,
                    "command": e.command,
                    "freecad_version": e.freecad_version,
                    "prompt": e.prompt,
                    "success": e.success,
                    "result": e.result,
                }
                for e in events
            ]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    async with AsyncSessionLocal() as db:
        try:
            machines = await db.execute(select(func.count(Machine.id)))
            total_machines = machines.scalar() or 0

            sessions = await db.execute(select(func.count(SessionModel.id)))
            total_sessions = sessions.scalar() or 0

            events = await db.execute(select(func.count(Event.id)))
            total_events = events.scalar() or 0

            cutoff = time.time() - 86400
            recent = await db.execute(
                select(func.count(Event.id)).where(Event.timestamp >= cutoff)
            )
            events_24h = recent.scalar() or 0

            dialect = engine.dialect.name
            if dialect == "postgresql":
                size_result = await db.execute(
                    text("SELECT pg_database_size(current_database())")
                )
                size_bytes = size_result.scalar() or 0
            else:
                size_result = await db.execute(
                    text("SELECT page_count * page_size FROM pragma_page_count, pragma_page_size")
                )
                size_bytes = size_result.scalar() or 0

            return StatsResponse(
                total_machines=total_machines,
                total_sessions=total_sessions,
                total_events=total_events,
                events_last_24h=events_24h,
                db_size_mb=round(size_bytes / (1024 * 1024), 2),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    # Default to localhost so the app is only reachable through nginx in prod.
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "7000"))
    logger.info("Starting telemetry receiver on http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port)
