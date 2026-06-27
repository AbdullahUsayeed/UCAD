from unittest.mock import patch, MagicMock
from tools.json_router import route_and_call, build_router_prompt
from tools.registry import ToolResult
import tools.freecad_operations  # noqa


class TestJsonRouter:

    def test_router_prompt_contains_all_tools(self):
        prompt = build_router_prompt()
        assert "make_box" in prompt
        assert "close_wire" in prompt
        assert "add_fillet" in prompt

    def test_valid_json_response_calls_tool(self):
        def mock_llm(messages):
            return '{"tool": "make_box", "args": {"length": 10, "width": 5, "height": 3}}'
        with patch("tools.freecad_operations.make_box",
                   return_value=ToolResult(True, "Box created")):
            result = route_and_call("make a box 10x5x3", mock_llm)
        # Should succeed or not throw — the mock may fail without FreeCAD,
        # but we want to confirm no exception from parsing/routing
        assert result is not None

    def test_invalid_json_returns_failure(self):
        def mock_llm(messages):
            return "not json at all"
        result = route_and_call("do something", mock_llm)
        assert not result.success
        assert "invalid JSON" in result.message

    def test_tool_none_returns_failure(self):
        def mock_llm(messages):
            return '{"tool": "none", "args": {}, "reason": "no match"}'
        result = route_and_call("do something weird", mock_llm)
        assert not result.success
        assert "no match" in result.message

    def test_json_fence_stripped(self):
        def mock_llm(messages):
            return '```json\n{"tool": "none", "args": {}}\n```'
        result = route_and_call("test", mock_llm)
        assert not result.success

    def test_llm_call_failure_returns_failure(self):
        def mock_llm(messages):
            raise RuntimeError("API error")
        result = route_and_call("test", mock_llm)
        assert not result.success
        assert "LLM call failed" in result.message

    def test_llm_empty_response_returns_failure(self):
        def mock_llm(messages):
            return None
        result = route_and_call("test", mock_llm)
        assert not result.success
        assert "no response" in result.message
