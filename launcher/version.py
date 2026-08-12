"""Component version tracking for UCAD Assistant.

Each component is versioned independently for granular updates.
"""
from dataclasses import dataclass


@dataclass
class ComponentVersion:
    name: str
    version: str
    min_freecad: str = "1.0.0"


# ── Component Versions ──────────────────────────────────────
# Bump these independently when making changes.

LAUNCHER_VERSION  = ComponentVersion("launcher",  "1.0.0")
PLUGIN_VERSION    = ComponentVersion("plugin",    "1.1.1")
RUNTIME_VERSION   = ComponentVersion("runtime",   "1.0.0")


ALL_COMPONENTS = [LAUNCHER_VERSION, PLUGIN_VERSION, RUNTIME_VERSION]


def version_summary() -> str:
    lines = ["UCAD Assistant Components:"]
    for c in ALL_COMPONENTS:
        lines.append(f"  {c.name}: v{c.version}")
    return "\n".join(lines)
