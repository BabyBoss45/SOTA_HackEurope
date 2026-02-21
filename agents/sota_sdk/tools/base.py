"""
BaseTool -- Anthropic-tool-calling-compatible tool abstraction.

Copied from agents/src/shared/tool_base.py (works with Anthropic as-is).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BaseTool(BaseModel, ABC):
    """
    Abstract base for every agent tool.

    Subclasses MUST define:
      - name:        unique tool identifier
      - description: what the tool does (shown to the LLM)
      - parameters:  JSON Schema dict for the tool's arguments
      - execute(**kwargs) -> str:  async implementation
    """

    name: str = ""
    description: str = ""
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
    })

    class Config:
        arbitrary_types_allowed = True

    def to_anthropic_tool(self) -> dict:
        """Return the Anthropic tool schema for this tool."""
        return {
            "name": self.name,
            "description": self.description.strip(),
            "input_schema": self.parameters,
        }

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Run the tool and return a JSON-serialisable string result."""
        ...

    async def __call__(self, **kwargs: Any) -> str:
        return await self.execute(**kwargs)
