"""Diagnostics screen — validates all system components before launch.

Provides a one-click health check that tests:
  ✓ Internet connectivity
  ✓ API key + provider reachability
  ✓ FreeCAD installation + version
  ✓ Mod integrity
  ✓ Python environment
  ✓ Configuration file integrity
"""
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from .paths import BASE, CONFIG_FILE, SECRETS_FILE, MOD, FREECAD
from .config_manager import load_config, load_secrets
from .version import PLUGIN_VERSION


@dataclass
class CheckResult:
    name: str
    status: bool  # True = pass, False = fail
    detail: str = ""
    duration_ms: float = 0.0


@dataclass
class DiagnosticsReport:
    checks: list[CheckResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    os_info: str = field(default_factory=lambda: f"{platform.system()} {platform.release()} ({platform.version()})")
    ucad_version: str = field(default_factory=lambda: PLUGIN_VERSION.version)
    python_version: str = sys.version

    @property
    def all_pass(self) -> bool:
        return all(c.status for c in self.checks)

    def to_text(self) -> str:
        lines = [
            f"UCAD Assistant Diagnostics",
            f"{'='*40}",
            f"Timestamp: {self.timestamp}",
            f"OS: {self.os_info}",
            f"Python: {self.python_version}",
            f"UCAD Home: {BASE}",
            f"UCAD Version: {self.ucad_version}",
            f"",
            f"Checks:",
            f"{'-'*40}",
        ]
        for c in self.checks:
            icon = "OK" if c.status else "FAIL"
            lines.append(f"  [{icon}] {c.name} ({c.duration_ms:.0f}ms)")
            if c.detail:
                lines.append(f"     {c.detail}")
        lines.append(f"{'='*40}")
        return "\n".join(lines)


def run_diagnostics() -> DiagnosticsReport:
    """Run all checks and return a report."""
    report = DiagnosticsReport()
    cfg = load_config()
    secrets = load_secrets()

    # 1. Internet
    _check_internet(report)

    # 2. API Key + Provider
    _check_api(report, cfg, secrets)

    # 4. FreeCAD
    _check_freecad(report)

    # 5. Mod
    _check_mod(report)

    # 6. Config file
    _check_config(report, cfg, secrets)

    # 7. Python deps
    _check_deps(report)

    return report


def _check_internet(report: DiagnosticsReport) -> None:
    t0 = time.time()
    try:
        import urllib.request
        urllib.request.urlopen("https://8.8.8.8", timeout=5)
        report.checks.append(CheckResult("Internet", True, "Connected", (time.time() - t0) * 1000))
    except Exception as e:
        report.checks.append(CheckResult("Internet", False, str(e), (time.time() - t0) * 1000))


def _check_api(report: DiagnosticsReport, cfg: dict, secrets: dict) -> None:
    provider = cfg.get("provider", "")
    api_key = secrets.get("api_key", "")
    model = cfg.get("model", "")

    if not provider or provider in ("ollama", "templates"):
        report.checks.append(CheckResult("API Key", True, f"No key needed for {provider}"))
        if provider == "ollama":
            _check_ollama(report, cfg)
        return

    if not api_key:
        report.checks.append(CheckResult("API Key", False, f"No API key configured for {provider}"))
        return

    t0 = time.time()
    try:
        from orchestrator.providers import LiteLLMAdapter
        adapter = LiteLLMAdapter(provider, api_key)
        ok, msg = adapter.check_connection()
        report.checks.append(CheckResult(
            f"{provider} API",
            ok,
            msg if not ok else f"Connected, model: {model or 'default'}",
            (time.time() - t0) * 1000,
        ))
    except Exception as e:
        report.checks.append(CheckResult(f"{provider} API", False, str(e), (time.time() - t0) * 1000))


def _check_ollama(report: DiagnosticsReport, cfg: dict) -> None:
    t0 = time.time()
    url = cfg.get("ollama_url", "http://localhost:11434")
    try:
        import requests
        r = requests.get(url.rstrip("/") + "/api/tags", timeout=5)
        if r.ok:
            models = [m["name"] for m in r.json().get("models", [])]
            report.checks.append(CheckResult("Ollama", True, f"Running. Models: {', '.join(models[:5])}", (time.time() - t0) * 1000))
        else:
            report.checks.append(CheckResult("Ollama", False, f"Responded {r.status_code}", (time.time() - t0) * 1000))
    except Exception as e:
        report.checks.append(CheckResult("Ollama", False, str(e), (time.time() - t0) * 1000))


def _check_freecad(report: DiagnosticsReport) -> None:
    from .runtime_manager import RuntimeManager
    t0 = time.time()
    rm = RuntimeManager()
    exe = rm.find_freecad()
    if exe:
        ver = rm.version_str
        report.checks.append(CheckResult("FreeCAD", True, f"{exe} (v{ver})", (time.time() - t0) * 1000))
    else:
        report.checks.append(CheckResult("FreeCAD", False, "Not found", (time.time() - t0) * 1000))


def _check_mod(report: DiagnosticsReport) -> None:
    t0 = time.time()
    init_py = MOD / "Init.py"
    init_gui = MOD / "InitGui.py"
    package = MOD / "package.xml"

    if not MOD.exists():
        report.checks.append(CheckResult("UCAD Mod", False, "Mod directory not found", (time.time() - t0) * 1000))
        return

    missing = [f.name for f in [init_py, init_gui, package] if not f.exists()]
    if missing:
        report.checks.append(CheckResult("UCAD Mod", False, f"Missing: {', '.join(missing)}", (time.time() - t0) * 1000))
    else:
        report.checks.append(CheckResult("UCAD Mod", True, f"Found at {MOD}", (time.time() - t0) * 1000))


def _check_config(report: DiagnosticsReport, cfg: dict, secrets: dict) -> None:
    t0 = time.time()
    issues = []
    if not CONFIG_FILE.exists():
        issues.append("config.json missing")
    if not secrets:
        issues.append("No secrets found (API key may be missing)")
    if not cfg.get("provider"):
        issues.append("No provider configured")
    if issues:
        report.checks.append(CheckResult("Configuration", False, "; ".join(issues), (time.time() - t0) * 1000))
    else:
        report.checks.append(CheckResult("Configuration", True, f"{cfg.get('provider', '?')} / {cfg.get('model', '?')}", (time.time() - t0) * 1000))


def _check_deps(report: DiagnosticsReport) -> None:
    t0 = time.time()
    required = ["litellm", "ezdxf", "shapely", "requests"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        report.checks.append(CheckResult("Python Dependencies", False, f"Missing: {', '.join(missing)}", (time.time() - t0) * 1000))
    else:
        report.checks.append(CheckResult("Python Dependencies", True, "All required packages installed", (time.time() - t0) * 1000))
