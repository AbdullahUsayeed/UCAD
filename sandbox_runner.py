"""Reliable process-level sandbox for executing AI-generated FreeCAD Python code.

Improvements over the original:
  - Multi-strategy FreeCAD detection with clear diagnostics on failure.
  - AST-based static validation as a fast first-pass (no subprocess needed).
  - Graceful fallback: if FreeCAD subprocess is unavailable, AST validation
    still runs so the user is never silently blocked.
  - Sandbox health-check on startup so failures are caught early, not mid-session.
  - Detailed error reports that distinguish between "FreeCAD not found",
    "syntax error in script", "runtime error", and "timeout".
  - Windows-aware: searches registry and common versioned install dirs.
  - sandbox_mode=False now only skips the subprocess, AST validation still runs.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TIMEOUT_S: int = 30
MEMORY_LIMIT_MB: int = 512

# Environment variable the user can set to pin the FreeCAD binary explicitly.
FREECAD_BIN_ENV_VAR = "FREECAD_BIN"

# ---------------------------------------------------------------------------
# Dangerous patterns for AST / regex static analysis
# ---------------------------------------------------------------------------

# Modules that should never be imported in generated code.
_BANNED_MODULES = {
    "subprocess", "socket", "http", "urllib", "requests", "ftplib",
    "smtplib", "telnetlib", "xmlrpc", "multiprocessing", "ctypes",
    "cffi", "winreg", "nt",
}

# Built-in names that are dangerous when called directly.
_BANNED_BUILTINS = {"eval", "exec", "compile", "__import__", "open", "breakpoint"}

# Regex fast-check before AST parse (catches obvious injections quickly).
_FAST_REJECT_RE = re.compile(
    r"\b(subprocess|socket\.connect|os\.system|os\.popen"
    r"|shutil\.rmtree|shutil\.move"
    r"|open\s*\(.*['\"]w['\"]"   # open(..., "w") — write attempts
    r"|eval\s*\(|exec\s*\()\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# FreeCAD detection — multi-strategy, with registry fallback on Windows
# ---------------------------------------------------------------------------

def _windows_registry_paths() -> list[str]:
    """Read FreeCAD install paths from the Windows registry."""
    paths: list[str] = []
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (
                r"SOFTWARE\FreeCAD",
                r"SOFTWARE\WOW6432Node\FreeCAD",
            ):
                try:
                    key = winreg.OpenKey(root, sub)
                    install_dir, _ = winreg.QueryValueEx(key, "InstallPath")
                    candidate = str(Path(install_dir) / "bin" / "FreeCADCmd.exe")
                    paths.append(candidate)
                    winreg.CloseKey(key)
                except OSError:
                    pass
    except ImportError:
        pass
    return paths


def _candidate_paths() -> list[str]:
    """Return an ordered list of FreeCAD binary candidates for this platform."""
    candidates: list[str] = []

    # 1. Explicit env var — highest priority.
    env_bin = os.environ.get(FREECAD_BIN_ENV_VAR, "").strip()
    if env_bin:
        candidates.append(env_bin)

    if sys.platform == "win32":
        # 2. Windows registry
        candidates.extend(_windows_registry_paths())

        # 3. Common versioned install directories
        prog_files = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.path.expanduser(r"~\AppData\Local\Programs"),
        ]
        versions = ["", " 1.0", " 1.1", " 0.21", " 0.20", " 0.19"]
        for base in prog_files:
            for ver in versions:
                candidates.append(
                    str(Path(base) / f"FreeCAD{ver}" / "bin" / "FreeCADCmd.exe")
                )

        # 4. Portable / user installs
        candidates += [
            os.path.expanduser(r"~\AppData\Local\FreeCAD\bin\FreeCADCmd.exe"),
            os.path.expanduser(r"~\FreeCAD\bin\FreeCADCmd.exe"),
        ]

    elif sys.platform == "darwin":
        candidates += [
            "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd",
            os.path.expanduser("~/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd"),
        ]

    else:  # Linux / other POSIX
        candidates += [
            "/usr/bin/freecadcmd",
            "/usr/local/bin/freecadcmd",
            "/snap/bin/freecad",
            "/usr/lib/freecad/bin/freecad",
            "/opt/freecad/bin/freecadcmd",
            os.path.expanduser("~/.local/bin/freecadcmd"),
        ]

    # 5. PATH search — last resort, works for any platform
    for name in ("freecadcmd", "FreeCADCmd", "freecad", "FreeCAD"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    return candidates


def detect_freecad(raise_on_missing: bool = True) -> Optional[str]:
    """Return the path to the best available FreeCAD executable, or None.

    Unlike the original, this never raises unexpectedly — call with
    raise_on_missing=False to get None when FreeCAD is absent.
    """
    seen: set[str] = set()
    for candidate in _candidate_paths():
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        p = Path(candidate)
        if p.is_file() and os.access(candidate, os.X_OK):
            return candidate

    if raise_on_missing:
        raise FileNotFoundError(
            "FreeCAD executable not found.\n"
            f"Set the {FREECAD_BIN_ENV_VAR} environment variable to the full path "
            "of FreeCADCmd.exe (Windows) or freecadcmd (Linux/macOS).\n"
            "Example (Windows): set FREECAD_BIN=C:\\Program Files\\FreeCAD 1.0\\bin\\FreeCADCmd.exe"
        )
    return None


# ---------------------------------------------------------------------------
# AST-based static validator — fast, no subprocess required
# ---------------------------------------------------------------------------

class _SecurityVisitor(ast.NodeVisitor):
    """Walk the AST and collect security violations."""

    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in _BANNED_MODULES:
                self.violations.append(
                    f"Line {node.lineno}: banned import '{alias.name}'"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        top = module.split(".")[0]
        if top in _BANNED_MODULES:
            self.violations.append(
                f"Line {node.lineno}: banned import from '{module}'"
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Detect eval(...), exec(...), __import__(...) etc.
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name and name in _BANNED_BUILTINS:
            self.violations.append(
                f"Line {node.lineno}: banned call '{name}()'"
            )
        self.generic_visit(node)


def validate_ast(script: str) -> dict:
    """Parse and statically analyse *script*.

    Returns a result dict compatible with run_sandboxed():
        ok, stdout, stderr, exit_code, timed_out
    """
    # Quick regex pre-check
    match = _FAST_REJECT_RE.search(script)
    if match:
        return _err(f"Static analysis: suspicious pattern detected: '{match.group()}'")

    # Parse
    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        return _err(f"Syntax error on line {e.lineno}: {e.msg}")

    # Walk AST
    visitor = _SecurityVisitor()
    visitor.visit(tree)
    if visitor.violations:
        return _err("Static analysis violations:\n" + "\n".join(visitor.violations))

    return _ok("AST validation passed.")


# ---------------------------------------------------------------------------
# Subprocess sandbox
# ---------------------------------------------------------------------------

def _build_env() -> dict[str, str]:
    """Minimal, safe environment for the FreeCAD subprocess."""
    return {k: os.environ.get(k, "") for k in (
        "PATH", "PYTHONPATH", "PYTHONHOME",
        "FREECAD_USER_HOME", "HOME", "USERPROFILE",
        "SYSTEMROOT", "TEMP", "TMP",       # Windows needs these
    )}


def _resource_limit_header() -> str:
    """Return Python lines to prepend that set OS resource limits."""
    if sys.platform == "linux":
        return (
            "import resource\n"
            f"resource.setrlimit(resource.RLIMIT_CPU, ({TIMEOUT_S}, {TIMEOUT_S + 5}))\n"
            f"resource.setrlimit(resource.RLIMIT_AS, "
            f"({MEMORY_LIMIT_MB * 1024 * 1024}, {MEMORY_LIMIT_MB * 1024 * 1024}))\n"
        )
    # Windows / macOS: rely on subprocess timeout instead
    return ""


def run_sandboxed(
    script: str,
    freecad_bin: Optional[str] = None,
    timeout: int = TIMEOUT_S,
    capture_output: bool = True,
) -> dict:
    """Execute *script* inside a FreeCAD subprocess with resource limits.

    If FreeCAD cannot be located, falls back to AST-only validation so the
    caller always gets a meaningful result rather than a silent failure.

    Returns dict: ok, stdout, stderr, exit_code, timed_out, validation_mode
    """
    # Always run AST check first — fast and catches most issues without subprocess.
    ast_result = validate_ast(script)
    if not ast_result["ok"]:
        ast_result["validation_mode"] = "ast_only"
        return ast_result

    # Locate FreeCAD binary
    if freecad_bin is None:
        freecad_bin = detect_freecad(raise_on_missing=False)

    if freecad_bin is None:
        # No FreeCAD found — return AST-pass result with a clear warning.
        return {
            **_ok(
                "AST validation passed. "
                f"WARNING: FreeCAD executable not found — set {FREECAD_BIN_ENV_VAR} "
                "for full subprocess validation."
            ),
            "validation_mode": "ast_only",
        }

    # Build the full script (resource limits + user code)
    # Append sys.exit(0) so FreeCAD exits after the script (on Windows,
    # --run-script drops into the Python REPL and never exits otherwise).
    script_exit = script.rstrip() + "\nimport sys; sys.exit(0)\n"
    full_script = _resource_limit_header() + script_exit

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(full_script)
            tmp_path = Path(tmp.name)

        result = subprocess.run(
            [freecad_bin, "--console", "--run-script", str(tmp_path)],
            capture_output=capture_output,
            timeout=timeout,
            env=_build_env(),
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.decode("utf-8", errors="replace") if capture_output else "",
            "stderr": result.stderr.decode("utf-8", errors="replace") if capture_output else "",
            "exit_code": result.returncode,
            "timed_out": False,
            "validation_mode": "subprocess",
        }

    except subprocess.TimeoutExpired:
        return {**_err(f"Sandbox timed out after {timeout}s."), "timed_out": True,
                "validation_mode": "subprocess"}
    except FileNotFoundError:
        # Binary disappeared between detection and execution — fall back.
        return {
            **_ok("AST validation passed (subprocess unavailable at execution time)."),
            "validation_mode": "ast_only",
        }
    except Exception as e:
        return {**_err(f"Sandbox process error: {e}"), "validation_mode": "subprocess"}
    finally:
        if tmp_path:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Pre-flight / mutation-stripped validation (replaces original validate_in_sandbox)
# ---------------------------------------------------------------------------

_MUTATION_RE = re.compile(
    r"\b(addObject|removeObject|deleteObject|cut|fuse|makeCompound"
    r"|export|saveAs|write|recompute|setattr|__import__)\s*\(",
    re.IGNORECASE,
)


def validate_in_sandbox(script: str) -> dict:
    """Pre-flight check: AST-validate then optionally subprocess-validate.

    Mutation calls (addObject, export, etc.) are stripped before the
    subprocess run so the check remains read-only. AST validation runs
    on the *original* script — it shouldn't contain banned patterns
    regardless of mutation stripping.
    """
    # AST-check the real script first
    ast_result = validate_ast(script)
    if not ast_result["ok"]:
        ast_result["validation_mode"] = "ast_only"
        return ast_result

    # Strip mutations for the subprocess pre-flight
    safe_lines = []
    for line in script.splitlines():
        if _MUTATION_RE.search(line):
            safe_lines.append(f"# stripped: {line.strip()}")
        else:
            safe_lines.append(line)

    return run_sandboxed("\n".join(safe_lines))


# ---------------------------------------------------------------------------
# Startup health check — call once at app init to surface problems early
# ---------------------------------------------------------------------------

def health_check() -> dict:
    """Run a trivial script through the full pipeline and report status.

    Returns dict: ok, freecad_bin, validation_mode, message
    """
    probe = "import FreeCAD\nprint('sandbox_ok')\n"
    freecad_bin = detect_freecad(raise_on_missing=False)

    result = run_sandboxed(probe, freecad_bin=freecad_bin)

    return {
        "ok": result["ok"],
        "freecad_bin": freecad_bin or "not found",
        "validation_mode": result.get("validation_mode", "unknown"),
        "message": (
            result["stdout"].strip() or result["stderr"].strip() or "no output"
        ),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(message: str) -> dict:
    return {"ok": True, "stdout": message, "stderr": "", "exit_code": 0, "timed_out": False}


def _err(message: str) -> dict:
    return {"ok": False, "stdout": "", "stderr": message, "exit_code": 1, "timed_out": False}
