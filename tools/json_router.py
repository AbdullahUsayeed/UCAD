import json
import re
from tools.registry import list_tools, call_tool, ToolResult


ROUTER_SYSTEM_PROMPT = """You are a FreeCAD tool dispatcher.
Given a user command, respond with ONLY a JSON object (no explanation, no markdown):

{{"tool": "<tool_name>", "args": {{...}}}}

Available tools:
{tool_list}

Rules:
- Pick the single best tool
- Fill args from the user command; use defaults for missing optional args
- If no tool fits, respond: {{"tool": "none", "args": {{}}, "reason": "explanation"}}
- Output raw JSON only — no ```json fences, no preamble
"""


def build_router_prompt() -> str:
    """Build the system prompt listing all available tools."""
    tools = list_tools()
    tool_lines = "\n".join(
        f'- {name}({", ".join(f"{k}" for k in info["params"])}): {info["description"]}'
        for name, info in tools.items()
    )
    return ROUTER_SYSTEM_PROMPT.format(tool_list=tool_lines)


def route_and_call(user_prompt: str, llm_callable) -> ToolResult:
    """
    Send user_prompt to LLM with tool list, parse JSON response,
    call the matching tool, return ToolResult.

    llm_callable: a function(messages: list[dict]) -> str | None
    that sends messages to the LLM and returns the response text.
    """
    system = build_router_prompt()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = llm_callable(messages)
    except Exception as e:
        return ToolResult(False, f"LLM call failed: {e}")

    if not raw:
        return ToolResult(False, "LLM returned no response.")

    raw = raw.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return ToolResult(False, f"LLM returned invalid JSON: {e}\nRaw: {raw!r}")

    tool_name = parsed.get("tool", "none")
    args = parsed.get("args", {})

    if tool_name == "none":
        reason = parsed.get("reason", "No matching tool.")
        return ToolResult(False, f"No tool matched: {reason}")

    return call_tool(tool_name, args)
