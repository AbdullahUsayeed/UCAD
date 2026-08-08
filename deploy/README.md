# Telemetry Server — Production Deployment

Receiver for the AICompanion FreeCAD addon. It collects usage + AI-generated
script data from every user's machine, stores it, and gives you clean JSONL
exports to train your own model.

- Server: `server.py` (FastAPI) + `database.py` (SQLAlchemy async)
- Client: `telemetry.py` built into the addon POSTs batches to `/api/events`

## Live deployment (this box)

The telemetry receiver runs on the shared Lightsail instance (`52.77.213.181`),
alongside the existing `redlightai.duckdns.org` site:

- **App:** `/opt/telemetry/` (venv + `server.py` + `database.py`)
- **DB:** SQLite at `/opt/telemetry/telemetry.db` (small box — no Postgres needed)
- **Service:** `telemetry.service` → gunicorn/uvicorn on `127.0.0.1:7999`
- **Proxy:** nginx `sites-available/telemetry-https` serves
  `https://ucadtelemetry.duckdns.org` (Let's Encrypt TLS) → `127.0.0.1:7999`.
  HTTP on port 80 redirects (301) to HTTPS. `/docs`/`/redoc` are not exposed.
- **Secrets:** `/etc/telemetry/env` (`DATABASE_URL`, `TELEMETRY_API_KEY`, `TELEMETRY_ADMIN_KEY`)

Why SQLite: the instance has ~1 GB RAM; installing PostgreSQL risks OOM.
`database.py`/`server.py` handle both dialects transparently. If you outgrow
it, set `DATABASE_URL` to `postgresql+asyncpg://...` and reinstall `asyncpg`.

## Auth model (two keys)

| Key | Where it lives | Grants |
|---|---|---|
| `TELEMETRY_API_KEY` | shipped inside the addon (public, open source) | `POST /api/events` only |
| `TELEMETRY_ADMIN_KEY` | `/etc/telemetry/env` on the server only — **never ship/commit it** | `GET`/`DELETE /api/events/{machine_id}`, `GET /api/stats` |

The public ingest key **cannot** read or delete data: those endpoints return
`403` unless the admin key is presented. If `TELEMETRY_ADMIN_KEY` is unset,
read/delete/stats are disabled entirely.

## How the data is arranged (30 users, no setup needed)

Every user machine gets a random persistent `machine_id` (stored in their local
`telemetry_cache.db`). Every FreeCAD launch creates a random `session_id`.
Each command becomes one `events` row. So with 30 users you automatically get
a clean hierarchy — no partitioning config needed:

```
machines  (≤30 rows — one per user machine)
  └─ sessions (many per user — one per FreeCAD run)
       └─ events (one row per command / AI script)
```

Query patterns:
- Per-user totals: `SELECT machine_id, count(*) FROM events GROUP BY 1;`
- A user's workflow: filter by `machine_id`, order by `timestamp`.
- Your training corpus: `SELECT ... WHERE source = 'ai_script'` (prompt → code → result).

`source` values: `gui_command`, `run_command`, `console_input`, `console_output`, `ai_script`.

## Redeploying after a code change

```bash
scp -i mykeyaws.pem server.py database.py ubuntu@52.77.213.181:/opt/telemetry/
ssh -i mykeyaws.pem ubuntu@52.77.213.181 "sudo chown telemetry:telemetry /opt/telemetry/server.py /opt/telemetry/database.py && sudo systemctl restart telemetry"
```

## Pointing the addon at your server

The addon resolves the URL + key from (highest priority first):
1. env vars `AICOMPANION_TELEMETRY_URL` / `AICOMPANION_TELEMETRY_KEY`
2. `telemetry_url` / `telemetry_key` in the addon's `config.json`
3. built-in defaults (URL = `https://ucadtelemetry.duckdns.org/api/events`,
   key = the public ingest token baked into `telemetry.py`)

Every request must include the header `X-Api-Key: <key>` (already handled by
`telemetry.py`). `/health` is public so clients can probe reachability; all
other endpoints require a valid key. The addon only ever sends the **ingest**
key, so it can POST events but never read or delete data.

## Consent

The addon shows a one-time consent dialog before telemetry starts. Users who
decline never send data. The setting can be toggled in Settings → "Share
anonymous usage statistics".

## HTTPS (live)

Telemetry is served over TLS at `https://ucadtelemetry.duckdns.org` (Let's
Encrypt, auto-renews). HTTP on port 80 redirects (301) to HTTPS, and the
cert is trusted by the client's default urllib verification.

To obtain the cert (if ever redeploying on a new box):
1. Point a duckdns domain at the instance IP and verify DNS.
2. `sudo certbot certonly --standalone -d <domain>.duckdns.org` (nginx must be
   stopped for the challenge).
3. Install `deploy/telemetry-https-nginx.conf` (edit the domain to match) and
   `sudo systemctl reload nginx`.

## Export training data

```bash
sudo -u telemetry /opt/telemetry/venv/bin/python /opt/telemetry/train-export.py --help
```

Run locally instead (from any machine with DB access):
```bash
export DATABASE_URL="sqlite+aiosqlite:////opt/telemetry/telemetry.db"
python deploy/train-export.py scripts > training.jsonl
```

Modes:
- `scripts` — `{prompt, code, success, result, ...}` pairs from AI scripts. Use
  this to fine-tune a code-generation model.
- `commands` — full ordered command sequences per session. Use for workflow models.

## Operations cheatsheet

| Task | Command |
|---|---|
| Service status | `sudo systemctl status telemetry` |
| Tail logs | `sudo journalctl -u telemetry -f` |
| Restart after code change | `sudo systemctl restart telemetry` |
| Query DB | `sudo sqlite3 /opt/telemetry/telemetry.db 'select * from events limit 10;'` |
| Rotate secrets | edit `/etc/telemetry/env`, `sudo systemctl restart telemetry` |
| DB backup | `sudo cp /opt/telemetry/telemetry.db backup-$(date +%F).db` |

## Scaling notes

- The default `GUNICORN_WORKERS=1` + nginx rate limiting handles 30 users easily.
- App binds only to `127.0.0.1:7999`; nginx owns the public port.
- In-memory rate limiting is per-worker; nginx enforces the real per-IP limit.
- If you outgrow one box, the schema already supports horizontal scaling —
  move `sessions`/`events` to managed Postgres and keep the app stateless.

