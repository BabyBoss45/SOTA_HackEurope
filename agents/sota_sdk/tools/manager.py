"""
ToolManager -- registry that holds BaseTool instances.

Copied from agents/src/shared/tool_base.py (works with Anthropic as-is).
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional, Sequence

from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolManager:
    """
    Registry of :class:`BaseTool` instances.

    Provides:
    * ``to_anthropic_tools()`` -- list of Anthropic tool schemas
    * ``call(name, arguments)`` -- dispatch + execute a tool by name
    """

    def __init__(self, tools: Sequence[BaseTool] | None = None):
        self._tools: Dict[str, BaseTool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ValueError(
                f"Tool {type(tool).__name__} must have a non-empty name"
            )
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool: %s", tool.name)
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    @property
    def tools(self) -> List[BaseTool]:
        return list(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())

    def to_anthropic_tools(self) -> List[dict]:
        """List of tool schemas for ``anthropic.messages.create(tools=...)``."""
        return [t.to_anthropic_tool() for t in self._tools.values()]

    async def call(self, name: str, arguments: str | dict) -> str:
        """Look up a tool by *name*, parse *arguments*, call ``execute``."""
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {name}"})

        if isinstance(arguments, str):
            try:
                kwargs = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return json.dumps({"error": f"Invalid JSON arguments for {name}"})
        else:
            kwargs = arguments or {}

        try:
            return await tool.execute(**kwargs)
        except Exception as exc:
            logger.exception("Tool %s raised an exception", name)
            return json.dumps({"error": f"Tool {name} failed: {type(exc).__name__}"})
