"""Local DXF processor — wraps dxf_processor.py for in-process use.
Provides local DXF parsing and reports dependency status."""

import os
import enum
from typing import List, Dict, Any, Optional


class DepsStatus(enum.Enum):
    AVAILABLE = "available"
    MISSING_EZDXF = "missing_ezdxf"
    MISSING_SHAPELY = "missing_shapely"
    MISSING_BOTH = "missing_both"


_backend_processor = None
_deps_status = DepsStatus.MISSING_BOTH

try:
    import ezdxf
    _deps_status = DepsStatus.MISSING_SHAPELY
    try:
        import shapely
        _deps_status = DepsStatus.AVAILABLE
    except ImportError:
        pass
except ImportError:
    try:
        import shapely
        _deps_status = DepsStatus.MISSING_EZDXF
    except ImportError:
        _deps_status = DepsStatus.MISSING_BOTH

if _deps_status == DepsStatus.AVAILABLE:
    try:
        from dxf_processor import process_dxf as _backend_process_dxf
        _backend_processor = _backend_process_dxf
    except Exception:
        _backend_processor = None


def get_deps_status() -> DepsStatus:
    """Return whether local DXF processing dependencies are available."""
    return _deps_status


def get_deps_status_message() -> str:
    """Return a human-readable message about dependency status."""
    status = get_deps_status()
    messages = {
        DepsStatus.AVAILABLE: "Local DXF processing available",
        DepsStatus.MISSING_EZDXF: "ezdxf not installed — DXF processing requires 'pip install ezdxf shapely'",
        DepsStatus.MISSING_SHAPELY: "shapely not installed — DXF processing requires 'pip install ezdxf shapely'",
        DepsStatus.MISSING_BOTH: "ezdxf and shapely not installed — DXF processing requires 'pip install ezdxf shapely'",
    }
    return messages.get(status, "Unknown dependency status")


def is_available() -> bool:
    """Return True if local DXF processing is available."""
    return _deps_status == DepsStatus.AVAILABLE and _backend_processor is not None


def process_dxf(filepath: str, tolerance: Optional[float] = None,
                layers: Optional[List[str]] = None,
                merge_multipolygons: bool = True,
                auto_close: str = "off") -> Dict[str, Any]:
    """Process a DXF file locally.

    Wraps dxf_processor.py:process_dxf.

    Args:
        filepath: Path to the DXF file.
        tolerance: Simplification tolerance in mm (auto-scaled if None).
        layers: Only process entities on these layers (None = all).
        merge_multipolygons: Merge touching sub-geometries into one profile.
        auto_close: How to handle open entities ("off", "safe", "aggressive").

    Returns:
        Dict with keys: status, profiles, warnings, metadata.

    Raises:
        RuntimeError: If dependencies are not available.
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"DXF file not found: {filepath}")

    if _backend_processor is None:
        raise RuntimeError(
            f"Cannot process DXF locally: {get_deps_status_message()}"
        )

    return _backend_process_dxf(
        filepath,
        tolerance=tolerance,
        layers=layers,
        merge_multipolygons=merge_multipolygons,
        auto_close=auto_close
    )
