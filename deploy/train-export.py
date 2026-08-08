#!/usr/bin/env python3
"""
train-export.py — Export telemetry from PostgreSQL into JSONL for model training.

Two modes:

  scripts   (default) — Emits one JSON object per AI-generated script:
                        {"prompt", "code", "success", "result", "freecad_version",
                         "machine_id", "session_id", "timestamp", "doc_summary"}
                        Use this to fine-tune a model that writes FreeCAD Python.

  commands  — Emits one JSON object per event, preserving workflow order
              (grouped by session). Use this for behavior/workflow models.

Usage (run on the server or anywhere with DB access):
    export DATABASE_URL="postgresql+asyncpg://telemetry:pass@127.0.0.1:5432/telemetry"
    python train-export.py scripts > training_scripts.jsonl
    python train-export.py commands > training_commands.jsonl
    python train-export.py scripts --min-len 20 --only-success > scripts_filtered.jsonl

Piping to gzip keeps the export compact:
    python train-export.py scripts | gzip > training_scripts.jsonl.gz
"""

import argparse
import asyncio
import json
import os
import sys

import asyncpg


async def export_scripts(conn, min_len: int, only_success: bool):
    query = """
        SELECT machine_id, session_id, timestamp, freecad_version, doc_summary,
               command, prompt, success, result
        FROM events
        WHERE source = 'ai_script'
          AND command IS NOT NULL AND length(command) >= $1
          AND (prompt IS NOT NULL AND prompt <> '')
        ORDER BY timestamp ASC
    """
    if only_success:
        query += " AND success = TRUE"
    rows = await conn.fetch(query, min_len)
    for r in rows:
        rec = {
            "machine_id": r["machine_id"],
            "session_id": r["session_id"],
            "timestamp": r["timestamp"],
            "freecad_version": r["freecad_version"],
            "doc_summary": r["doc_summary"],
            "prompt": r["prompt"],
            "code": r["command"],
            "success": r["success"],
            "result": r["result"],
        }
        sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")


async def export_commands(conn, limit_per_session: int):
    query = """
        SELECT machine_id, session_id, timestamp, source, workbench,
               freecad_version, command, prompt, success
        FROM events
        WHERE source != 'ai_script'
        ORDER BY session_id ASC, timestamp ASC, id ASC
    """
    groups = {}
    async with conn.transaction():
        cur = await conn.cursor(query)
        while rows := await cur.fetch(500):
            for r in rows:
                g = groups.setdefault(
                    r["session_id"],
                    {"machine_id": r["machine_id"], "events": []},
                )
                if len(g["events"]) < limit_per_session:
                    g["events"].append(
                        {
                            "timestamp": r["timestamp"],
                            "source": r["source"],
                            "workbench": r["workbench"],
                            "command": r["command"],
                            "freecad_version": r["freecad_version"],
                        }
                    )
    for sid, g in groups.items():
        rec = {"session_id": sid, "machine_id": g["machine_id"], "events": g["events"]}
        sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")


async def main():
    parser = argparse.ArgumentParser(description="Export telemetry for model training.")
    parser.add_argument(
        "mode",
        choices=["scripts", "commands"],
        default="scripts",
        nargs="?",
        help="scripts: prompt/code/result pairs. commands: session workflows.",
    )
    parser.add_argument("--min-len", type=int, default=10,
                        help="scripts mode: minimum code length to include (default 10).")
    parser.add_argument("--only-success", action="store_true",
                        help="scripts mode: only export successful scripts.")
    parser.add_argument("--limit-per-session", type=int, default=500,
                        help="commands mode: max events per session (default 500).")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL (e.g. postgresql+asyncpg://user:pass@127.0.0.1:5432/telemetry)")
    # asyncpg wants its own scheme
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn)
    try:
        if args.mode == "scripts":
            await export_scripts(conn, args.min_len, args.only_success)
        else:
            await export_commands(conn, args.limit_per_session)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
