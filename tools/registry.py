from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import functools


@dataclass
class ToolResult:
    success: bool
    message: str
    data: dict = field(default_factory=dict)

    def __str__(self):
        status = "\u2705" if self.success else "\u274c"
        return f"{status} {self.message}"


_TOOLS: dict[str, dict] = {}


def cad_tool(description: str, params: dict = None):
    """
    Decorator that registers a function as a callable CAD tool.
    params: JSON-schema style param descriptions for the LLM prompt.

    Example:
        @cad_tool("Close the open wire in a sketch",
                  params={"sketch_name": "Name of the sketch object (optional)"})
        def close_wire(sketch_name: str = None) -> ToolResult:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        _TOOLS[fn.__name__] = {
            "function": fn,
            "description": description,
            "params": params or {},
        }
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def get_tool(name: str) -> Optional[dict]:
    return _TOOLS.get(name)


def list_tools() -> dict:
    return {
        name: {"description": t["description"], "params": t["params"]}
        for name, t in _TOOLS.items()
    }


def call_tool(name: str, args: dict) -> ToolResult:
    """Call a registered tool by name with a dict of arguments."""
    tool = _TOOLS.get(name)
    if not tool:
        return ToolResult(False, f"Unknown tool: {name!r}. Available: {list(_TOOLS.keys())}")
    try:
        result = tool["function"](**args)
        if not isinstance(result, ToolResult):
            return ToolResult(True, str(result))
        return result
    except TypeError as e:
        return ToolResult(False, f"Wrong arguments for {name!r}: {e}")
    except Exception as e:
        return ToolResult(False, f"{name!r} raised {type(e).__name__}: {e}")
