"""
telemetry.py — FreeCAD session telemetry collector.

Captures Python commands executed via FreeCAD's GUI, Python console, and
internal doCommand calls. Persists to local SQLite and uploads batches to
a remote server for ML training data collection.

Collection only starts after the user explicitly agrees to the consent
prompt. All errors are caught so telemetry never impacts the user.
"""

import FreeCAD
import FreeCADGui
import sys as _sys
import os as _os
import json
import sqlite3
import threading
import time
import uuid
import hashlib
import re
import urllib.request
import urllib.error

import ssl as _ssl

_HTTP_SSL_CONTEXT = None


def _http_context():
    """HTTPS context that avoids the deprecated PROTOCOL_TLS default path
    (which emits ssl.PROTOCOL_TLS is deprecated on Python 3.10+)."""
    global _HTTP_SSL_CONTEXT
    if _HTTP_SSL_CONTEXT is None:
        try:
            ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = True
            ctx.verify_mode = _ssl.CERT_REQUIRED
            ctx.load_default_certs()
            _HTTP_SSL_CONTEXT = ctx
        except Exception:
            _HTTP_SSL_CONTEXT = _ssl.create_default_context()
    return _HTTP_SSL_CONTEXT


_ADDON_DIR = _os.path.dirname(_os.path.abspath(__file__))
_LOG_PREFIX = "[AICompanion:Telemetry] "
_CONSENT_FILE = _os.path.join(_ADDON_DIR, "config.json")
_CONSENT_KEY = "telemetry_consent"
_CONSENT_ACCEPT = "accepted"
_CONSENT_DECLINE = "declined"


def _load_config():
    try:
        with open(_CONSENT_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_config(data):
    try:
        import tempfile
        fd, tmp_path = tempfile.mkstemp(prefix="config_", suffix=".tmp", dir=_ADDON_DIR, text=True)
        try:
            with _os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            _os.replace(tmp_path, _CONSENT_FILE)
        except Exception:
            try:
                _os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        pass


def _effective_server_url():
    """Server URL priority: env var → config.json → default."""
    env_url = _os.getenv("AICOMPANION_TELEMETRY_URL", "")
    if env_url:
        return env_url.rstrip("/") + "/api/events"
    cfg_url = _load_config().get("telemetry_url", "")
    if cfg_url:
        return cfg_url.rstrip("/") + "/api/events"
    return "https://ucadtelemetry.duckdns.org/api/events"


def _effective_api_key():
    """API key priority: env var → config.json → built-in ingest token.

    The built-in value is a public ingest token (the repo is open source); it
    gates write access so the endpoint isn't open to arbitrary POSTs. Set
    AICOMPANION_TELEMETRY_KEY or telemetry_key in config.json to override.
    """
    env_key = _os.getenv("AICOMPANION_TELEMETRY_KEY", "")
    if env_key:
        return env_key
    cfg_key = _load_config().get("telemetry_key", "")
    if cfg_key:
        return cfg_key
    return "xGfp1jesZw9SkQEcPKIi_DjO9HDRH1OaIuLLnbqNn0M"


SERVER_URL = _effective_server_url()
API_KEY = _effective_api_key()
FLUSH_INTERVAL = 30
BATCH_SIZE = 100
MAX_RETENTION_DAYS = 7
_MAX_CMD_LEN = 50000
_COMMIT_EVERY = 10
_MAX_RETRIES = 10


def has_consent():
    """Return True if the user accepted telemetry, False if declined,
    None if they have not been asked yet."""
    value = _load_config().get(_CONSENT_KEY)
    if value == _CONSENT_ACCEPT:
        return True
    if value == _CONSENT_DECLINE:
        return False
    return None


def record_consent(accepted):
    cfg = _load_config()
    cfg[_CONSENT_KEY] = _CONSENT_ACCEPT if accepted else _CONSENT_DECLINE
    _save_config(cfg)


def _log(msg):
    try:
        FreeCAD.Console.PrintLog(f"{_LOG_PREFIX}{msg}\n")
    except Exception:
        pass


def _warn(msg):
    try:
        FreeCAD.Console.PrintWarning(f"{_LOG_PREFIX}{msg}\n")
    except Exception:
        pass


def _get_machine_id():
    try:
        db = sqlite3.connect(_db_path(), timeout=5)
        cur = db.execute("SELECT value FROM meta WHERE key='machine_id'")
        row = cur.fetchone()
        if row:
            db.close()
            return row[0]
        mid = str(uuid.uuid4())
        db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('machine_id', ?)", (mid,))
        db.commit()
        db.close()
        return mid
    except Exception:
        return str(uuid.uuid4())


def _get_session_id():
    return str(uuid.uuid4())


def _get_workbench():
    try:
        wb = FreeCADGui.activeWorkbench()
        if wb:
            return getattr(wb, "MenuText", wb.__class__.__name__)
        return ""
    except Exception:
        return ""


def _get_freecad_version():
    try:
        return FreeCAD.VersionString()
    except Exception:
        pass
    try:
        ver = FreeCAD.Version
        if isinstance(ver, (list, tuple)):
            return ".".join(str(v) for v in ver[:3])
        if isinstance(ver, str):
            return ver.split(" ")[0]
        return str(ver)
    except Exception:
        return "unknown"


def _get_doc_summary():
    try:
        doc = FreeCAD.ActiveDocument
        if doc:
            objs = doc.Objects
            types = {}
            for o in objs:
                try:
                    tid = o.TypeId.split("::")[-1] if o.TypeId else "?"
                except Exception:
                    tid = "?"
                types[tid] = types.get(tid, 0) + 1
            return json.dumps({"count": len(objs), "types": types})
        return ""
    except Exception:
        return ""


def _db_path():
    return _os.path.join(_ADDON_DIR, "telemetry_cache.db")


def _init_db():
    db = sqlite3.connect(_db_path(), timeout=10, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            command TEXT NOT NULL,
            timestamp REAL NOT NULL,
            source TEXT NOT NULL DEFAULT 'gui_command',
            workbench TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            uploaded INTEGER NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_events_uploaded ON events(uploaded)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_events_retry ON events(uploaded, retry_count)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    try:
        db.execute("ALTER TABLE events ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE events ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    db.commit()
    return db


class TelemetryCollector:
    """Silently captures Python commands and uploads to Lightsail."""

    def __init__(self, server_url=SERVER_URL):
        self.server_url = server_url
        self.session_id = _get_session_id()
        self.machine_id = _get_machine_id()
        self._db = _init_db()
        self._db_lock = threading.Lock()
        self._running = True
        self._report_hook_installed = False
        self._commit_counter = 0

        if not self._server_reachable():
            _warn(f"Server {server_url} unreachable — events will queue locally")

        self._prune()
        self._count_session()

        self._flusher = threading.Thread(target=self._flush_loop, daemon=True)
        self._flusher.start()
        self._log_stats()

    def _server_reachable(self):
        try:
            base = self.server_url.replace("/api/events", "").replace("/api", "").rstrip("/")
            req = urllib.request.Request(f"{base}/health", method="GET")
            if API_KEY:
                req.add_header("X-Api-Key", API_KEY)
            resp = urllib.request.urlopen(req, timeout=5, context=_http_context())
            return resp.status == 200
        except Exception:
            return False

    def install_report_view_hook(self):
        try:
            from compat import QtCore, QtWidgets
            mw = FreeCADGui.getMainWindow()
            if not mw:
                return
            rv = mw.findChild(QtWidgets.QTextEdit, "Report view")
            if not rv:
                return
            self._install_report_hook(rv)
        except Exception:
            pass

    def install_do_command_hook(self):
        try:
            orig = FreeCADGui.doCommand
            collector = self
            def wrapper(cmd):
                if isinstance(cmd, str) and cmd.strip():
                    collector._capture(cmd, "gui_command")
                return orig(cmd)
            FreeCADGui.doCommand = wrapper
            _log("doCommand hook installed")
        except Exception:
            _warn("doCommand hook failed")

    def install_run_command_hook(self):
        try:
            orig = FreeCADGui.runCommand
            collector = self
            def wrapper(name, *args):
                if isinstance(name, str):
                    collector._capture(f"Gui.runCommand('{name}')", "run_command")
                return orig(name, *args)
            FreeCADGui.runCommand = wrapper
            _log("runCommand hook installed")
        except Exception:
            _warn("runCommand hook failed")

    def record_ai_script(self, prompt, code, success, result=""):
        """Record an AI-generated script for training data collection."""
        if not code or not isinstance(code, str):
            return
        code = code.strip()
        if not code:
            return
        try:
            metadata = json.dumps({
                "freecad_version": _get_freecad_version(),
                "doc_summary": _get_doc_summary(),
                "prompt": (prompt or "")[:2000],
                "success": bool(success),
                "result": (result or "")[:500],
            })
            with self._db_lock:
                self._db.execute(
                    """INSERT INTO events (session_id, machine_id, command, timestamp, source, workbench, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (self.session_id, self.machine_id, code[:_MAX_CMD_LEN],
                     time.time(), "ai_script", _get_workbench(), metadata),
                )
                self._commit_counter += 1
                if self._commit_counter >= _COMMIT_EVERY:
                    self._db.commit()
                    self._commit_counter = 0
            self._flush_if_full()
        except Exception:
            pass

    def _count_session(self):
        try:
            with self._db_lock:
                cur = self._db.execute("SELECT value FROM meta WHERE key='total_sessions'")
                row = cur.fetchone()
                total = (int(row[0]) + 1) if row else 1
                self._db.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('total_sessions', ?)",
                    (str(total),)
                )
                self._db.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_session', ?)",
                    (self.session_id,)
                )
                self._db.commit()
        except Exception:
            pass

    def get_stats(self):
        try:
            with self._db_lock:
                sessions = self._db.execute(
                    "SELECT value FROM meta WHERE key='total_sessions'"
                ).fetchone()
                events = self._db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                uploaded = self._db.execute(
                    "SELECT COUNT(*) FROM events WHERE uploaded = 1"
                ).fetchone()[0]
                ai_scripts = self._db.execute(
                    "SELECT COUNT(*) FROM events WHERE source='ai_script'"
                ).fetchone()[0]
            return {
                "sessions": int(sessions[0]) if sessions else 0,
                "total_events": events,
                "uploaded": uploaded,
                "ai_scripts": ai_scripts,
            }
        except Exception:
            return {}

    def _log_stats(self):
        try:
            s = self.get_stats()
            _log(
                f"Session #{s['sessions']} started | "
                f"{s['total_events']} total events | "
                f"{s['uploaded']} uploaded | "
                f"{s['ai_scripts']} ai_scripts"
            )
        except Exception:
            pass

    # ── Hooks ──────────────────────────────────────────────────────────────

    def _hook_report_view(self):
        try:
            from compat import QtCore, QtWidgets
            mw = FreeCADGui.getMainWindow()
            if not mw:
                QtCore.QTimer.singleShot(1000, self._hook_report_view)
                return
            rv = mw.findChild(QtWidgets.QTextEdit, "Report view")
            if not rv:
                QtCore.QTimer.singleShot(1000, self._hook_report_view)
                return
            self._install_report_hook(rv)
        except Exception:
            pass

    def _install_report_hook(self, rv):
        if self._report_hook_installed:
            return
        self._report_hook_installed = True
        try:
            collector = self
            _last = rv.toPlainText()
            def on_changed():
                nonlocal _last
                cur = rv.toPlainText()
                if len(cur) > len(_last):
                    diff = cur[len(_last):]
                    _last = cur
                    for line in diff.split("\n"):
                        s = line.strip()
                        if s:
                            collector._capture(s, "console_output")
                else:
                    _last = cur
            rv.textChanged.connect(on_changed)
            _log("Report view hook installed")
        except Exception:
            pass

    def _hook_do_command(self):
        original = getattr(FreeCADGui, "doCommand", None)
        if not callable(original):
            return
        collector = self
        def wrapper(cmd):
            if isinstance(cmd, str) and cmd.strip():
                collector._capture(cmd, "gui_command")
            return original(cmd)
        try:
            FreeCADGui.__dict__["doCommand"] = wrapper
        except Exception:
            pass

    def _hook_run_command(self):
        original = getattr(FreeCADGui, "runCommand", None)
        if not callable(original):
            return
        collector = self
        def wrapper(name, *args):
            if isinstance(name, str):
                collector._capture(f"Gui.runCommand('{name}')", "run_command")
            return original(name, *args)
        try:
            FreeCADGui.__dict__["runCommand"] = wrapper
        except Exception:
            pass

    def _hook_python_console(self):
        """Connect to the Python console's command signal.

        Tries multiple common FreeCAD widget names and connection methods
        across different FreeCAD versions. Retries via QTimer if the widget
        isn't available yet.
        """
        try:
            from compat import QtCore, QtWidgets
            mw = FreeCADGui.getMainWindow()
            if not mw:
                QtCore.QTimer.singleShot(2000, self._hook_python_console)
                return

            console = None
            for name in ("Python console", "PythonConsole", "Python_console",
                         "Console", "console"):
                console = mw.findChild(QtWidgets.QWidget, name)
                if console:
                    break

            if not console:
                for child in mw.findChildren(QtWidgets.QWidget):
                    cls = child.metaObject().className() if hasattr(child, 'metaObject') else ""
                    if "PythonConsole" in cls or "Console" in cls:
                        console = child
                        break

            if not console:
                QtCore.QTimer.singleShot(2000, self._hook_python_console)
                return

            collector = self

            if hasattr(console, "pythonCommand"):
                try:
                    console.pythonCommand.connect(
                        lambda cmd: collector._capture(cmd, "console_input")
                    )
                    _log("Python console hooked via pythonCommand signal")
                    return
                except Exception:
                    pass

            for edit in console.findChildren(QtWidgets.QPlainTextEdit):
                if hasattr(edit, "pythonCommand"):
                    edit.pythonCommand.connect(
                        lambda cmd: collector._capture(cmd, "console_input")
                    )
                    _log("Python console hooked via child QPlainTextEdit")
                    return

            edit = None
            if hasattr(console, "textChanged") and hasattr(console, "toPlainText"):
                edit = console
            else:
                for child in console.findChildren(QtWidgets.QWidget):
                    if hasattr(child, "textChanged") and hasattr(child, "toPlainText"):
                        edit = child
                        break

            if edit is not None:
                _last_console = edit.toPlainText()

                def _on_console_change():
                    nonlocal _last_console
                    try:
                        cur = edit.toPlainText()
                        if len(cur) > len(_last_console):
                            diff = cur[len(_last_console):]
                            _last_console = cur
                            for line in diff.split("\n"):
                                s = line.strip()
                                if s and not s.startswith(">>>") and not s.startswith("..."):
                                    collector._capture(s, "console_input")
                        else:
                            _last_console = cur
                    except Exception:
                        pass

                edit.textChanged.connect(_on_console_change)
                _log("Python console hooked via textChanged polling")
            else:
                _warn("Python console widget found but no signal available")

        except Exception:
            pass

    # ── Capture ────────────────────────────────────────────────────────────

    def _capture(self, command, source="gui_command"):
        if not command or not isinstance(command, str):
            return
        command = command.strip()
        if not command:
            return
        if source == "console_output":
            lower = command.lower()
            if any(skip in lower for skip in ("notice:", "warning:", "  #",
                                               "pyqt", "qt.core", "qpainter")):
                return
            if re.match(r"^\d{1,2}:\d{2}:\d{2}\s", command):
                return
        try:
            metadata = json.dumps({
                "freecad_version": _get_freecad_version(),
                "doc_summary": _get_doc_summary(),
            })
            with self._db_lock:
                self._db.execute(
                    """INSERT INTO events (session_id, machine_id, command, timestamp, source, workbench, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (self.session_id, self.machine_id, command[:_MAX_CMD_LEN],
                     time.time(), source, _get_workbench(), metadata),
                )
                self._commit_counter += 1
                if self._commit_counter >= _COMMIT_EVERY:
                    self._db.commit()
                    self._commit_counter = 0
        except Exception:
            pass
        self._flush_if_full()

    def _flush_if_full(self):
        try:
            with self._db_lock:
                count = self._db.execute(
                    "SELECT COUNT(*) FROM events WHERE uploaded = 0"
                ).fetchone()[0]
            if count >= BATCH_SIZE:
                threading.Thread(target=self._flush_once, daemon=True).start()
        except Exception:
            pass

    # ── Upload ─────────────────────────────────────────────────────────────

    def _flush_loop(self):
        _stats_interval = 300
        _next_stats = time.time() + _stats_interval
        while self._running:
            time.sleep(FLUSH_INTERVAL)
            try:
                self._flush_once()
            except Exception:
                pass
            if time.time() >= _next_stats:
                try:
                    self._log_stats()
                except Exception:
                    pass
                _next_stats = time.time() + _stats_interval

    def _flush_once(self):
        with self._db_lock:
            rows = self._db.execute(
                "SELECT id, session_id, machine_id, command, timestamp, source, workbench, metadata, retry_count "
                "FROM events WHERE uploaded = 0 AND retry_count < ? ORDER BY id ASC LIMIT ?",
                (_MAX_RETRIES, BATCH_SIZE)
            ).fetchall()
            if not rows:
                return
            ids = [r[0] for r in rows]

            events = []
            for r in rows:
                ev = {
                    "command": r[3],
                    "timestamp": r[4],
                    "source": r[5],
                    "workbench": r[6],
                }
                meta_raw = r[7]
                if meta_raw and meta_raw != "{}":
                    try:
                        meta = json.loads(meta_raw)
                        ev["freecad_version"] = meta.get("freecad_version", "")
                        ev["doc_summary"] = meta.get("doc_summary", "")
                        ev["prompt"] = meta.get("prompt", "")
                        if "success" in meta:
                            ev["success"] = bool(meta.get("success"))
                        ev["result"] = meta.get("result", "")
                    except (json.JSONDecodeError, TypeError):
                        pass
                events.append(ev)

            payload = {
                "session_id": rows[0][1],
                "machine_id": rows[0][2],
                "events": events,
            }

        try:
            data = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if API_KEY:
                headers["X-Api-Key"] = API_KEY
            req = urllib.request.Request(
                self.server_url,
                data=data,
                headers=headers,
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=15, context=_http_context())
            if resp.status == 200:
                self._mark_uploaded(ids)
            else:
                self._increment_retries(ids)
        except urllib.error.URLError as e:
            self._increment_retries(ids)
            if isinstance(e.reason, str) and "timed out" in e.reason.lower():
                pass
        except Exception:
            self._increment_retries(ids)

    def _mark_uploaded(self, ids):
        try:
            with self._db_lock:
                placeholders = ",".join("?" for _ in ids)
                self._db.execute(
                    f"UPDATE events SET uploaded = 1 WHERE id IN ({placeholders})",
                    ids,
                )
                self._db.commit()
        except Exception:
            pass

    def _increment_retries(self, ids):
        try:
            with self._db_lock:
                placeholders = ",".join("?" for _ in ids)
                self._db.execute(
                    f"UPDATE events SET retry_count = retry_count + 1 WHERE id IN ({placeholders})",
                    ids,
                )
                self._db.commit()
        except Exception:
            pass

    # ── Maintenance ────────────────────────────────────────────────────────

    def _prune(self):
        try:
            with self._db_lock:
                cutoff = time.time() - MAX_RETENTION_DAYS * 86400
                self._db.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
                self._db.execute("DELETE FROM events WHERE retry_count >= ?", (_MAX_RETRIES,))
                self._db.commit()
        except Exception:
            pass

    def shutdown(self):
        self._running = False
        try:
            self._flush_once()
        except Exception:
            pass
        try:
            self._log_stats()
        except Exception:
            pass
        try:
            with self._db_lock:
                if self._commit_counter > 0:
                    self._db.commit()
                self._db.close()
        except Exception:
            pass
        _log("Shutdown complete")
