"""Unit tests for sota_sdk.tools — BaseTool and ToolManager."""

import json

import pytest

from sota_sdk.tools.base import BaseTool
from sota_sdk.tools.manager import ToolManager

pytestmark = pytest.mark.unit


# ── Concrete tool for testing ────────────────────────────────────────────────

class EchoTool(BaseTool):
    name: str = "echo"
    description: str = "Echoes input"
    parameters: dict = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    async def execute(self, **kwargs) -> str:
        return kwargs.get("message", "")


class FailTool(BaseTool):
    name: str = "fail"
    description: str = "Always fails"

    async def execute(self, **kwargs) -> str:
        raise RuntimeError("Tool exploded")


class NoNameTool(BaseTool):
    description: str = "Missing name"

    async def execute(self, **kwargs) -> str:
        return "nope"


# ── BaseTool Tests ───────────────────────────────────────────────────────────

class TestBaseTool:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            BaseTool()

    def test_concrete_tool_instantiation(self):
        t = EchoTool()
        assert t.name == "echo"

    async def test_execute(self):
        t = EchoTool()
        result = await t.execute(message="hello")
        assert result == "hello"

    async def test_callable(self):
        t = EchoTool()
        result = await t(message="world")
        assert result == "world"

    def test_to_anthropic_tool_schema(self):
        t = EchoTool()
        schema = t.to_anthropic_tool()
        assert schema["name"] == "echo"
        assert schema["description"] == "Echoes input"
        assert schema["input_schema"]["type"] == "object"
        assert "message" in schema["input_schema"]["properties"]

    def test_default_parameters(self):
        class MinimalTool(BaseTool):
            name: str = "min"
            async def execute(self, **kwargs) -> str:
                return ""

        t = MinimalTool()
        assert t.parameters["type"] == "object"
        assert t.parameters["properties"] == {}


# ── ToolManager Tests ────────────────────────────────────────────────────────

class TestToolManager:
    def test_register_and_get(self):
        mgr = ToolManager()
        mgr.register(EchoTool())
        assert mgr.get("echo") is not None
        assert mgr.get("nonexistent") is None

    def test_len(self):
        mgr = ToolManager(tools=[EchoTool()])
        assert len(mgr) == 1

    def test_iter(self):
        mgr = ToolManager(tools=[EchoTool(), FailTool()])
        names = [t.name for t in mgr]
        assert "echo" in names
        assert "fail" in names

    def test_constructor_with_tools(self):
        mgr = ToolManager(tools=[EchoTool(), FailTool()])
        assert len(mgr) == 2

    def test_register_empty_name_raises(self):
        mgr = ToolManager()
        with pytest.raises(ValueError, match="non-empty name"):
            mgr.register(NoNameTool())

    async def test_call_with_dict_args(self):
        mgr = ToolManager(tools=[EchoTool()])
        result = await mgr.call("echo", {"message": "hi"})
        assert result == "hi"

    async def test_call_with_json_string_args(self):
        mgr = ToolManager(tools=[EchoTool()])
        result = await mgr.call("echo", '{"message": "hi"}')
        assert result == "hi"

    async def test_call_unknown_tool(self):
        mgr = ToolManager()
        result = await mgr.call("nope", {})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "Unknown tool" in parsed["error"]

    async def test_call_tool_exception_sanitized(self):
        mgr = ToolManager(tools=[FailTool()])
        result = await mgr.call("fail", {})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "RuntimeError" in parsed["error"]

    def test_to_anthropic_tools(self):
        mgr = ToolManager(tools=[EchoTool(), FailTool()])
        schemas = mgr.to_anthropic_tools()
        assert len(schemas) == 2
        names = {s["name"] for s in schemas}
        assert names == {"echo", "fail"}

    async def test_call_with_empty_string_args(self):
        class NoArgTool(BaseTool):
            name: str = "noarg"
            async def execute(self, **kwargs) -> str:
                return "ok"
        mgr = ToolManager(tools=[NoArgTool()])
        result = await mgr.call("noarg", "")
        assert result == "ok"

    async def test_call_invalid_json_string(self):
        mgr = ToolManager(tools=[EchoTool()])
        result = await mgr.call("echo", "not json")
        parsed = json.loads(result)
        assert "error" in parsed
        assert "Invalid JSON" in parsed["error"]

    def test_tools_property(self):
        mgr = ToolManager(tools=[EchoTool()])
        assert len(mgr.tools) == 1
        assert mgr.tools[0].name == "echo"
