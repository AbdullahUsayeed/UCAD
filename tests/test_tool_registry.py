from tools.registry import call_tool, list_tools, ToolResult
import tools.freecad_operations  # noqa — register tools


class TestToolRegistry:

    def test_list_tools_returns_all_registered(self):
        tools = list_tools()
        expected = ["close_wire", "add_fillet", "make_box", "make_pad",
                    "select_object", "delete_object", "set_visibility",
                    "measure_distance", "list_objects", "fit_view",
                    "recompute", "set_property"]
        for name in expected:
            assert name in tools, f"Tool {name!r} not registered"

    def test_call_unknown_tool_returns_failure(self):
        result = call_tool("nonexistent_tool", {})
        assert not result.success
        assert "Unknown tool" in result.message

    def test_call_tool_wrong_args_returns_failure(self):
        result = call_tool("make_box", {"wrong_key": 999})
        assert not result.success

    def test_tool_result_str_pass(self):
        r = ToolResult(True, "Done")
        assert "\u2705" in str(r)

    def test_tool_result_str_fail(self):
        r = ToolResult(False, "Error")
        assert "\u274c" in str(r)

    def test_make_box_requires_three_dimensions(self):
        result = call_tool("make_box", {"length": 10, "width": 5})
        assert not result.success
        assert "make_box" in result.message

    def test_all_tools_have_descriptions(self):
        for name, info in list_tools().items():
            assert info["description"], f"Tool {name!r} has no description"
            assert isinstance(info["params"], dict), \
                f"Tool {name!r} params must be a dict"

    def test_tool_registry_count(self):
        tools = list_tools()
        assert len(tools) >= 12, f"Expected at least 12 tools, got {len(tools)}"
