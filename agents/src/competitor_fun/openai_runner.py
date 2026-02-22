"""
OpenAI Agent Runner — GPT-4o-powered tool-calling agent loop.

Drop-in alternative to the Anthropic AgentRunner, using the OpenAI
Chat Completions API with function calling.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from ..shared.tool_base import ToolManager

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  OpenAI LLM Client
# ──────────────────────────────────────────────────────────────

class OpenAILLMClient:
    """
    Thin wrapper around ``openai.AsyncOpenAI`` for chat completions
    with tool/function-calling support.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = AsyncOpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
        )

    async def chat(
        self,
        messages: List[dict],
        tools: List[dict] | None = None,
        system: str | None = None,
    ) -> Any:
        """
        Send a chat completions request and return the raw response.
        """
        full_messages: List[dict] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": full_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self._client.chat.completions.create(**kwargs)
        return response


# ──────────────────────────────────────────────────────────────
#  OpenAI AgentRunner
# ──────────────────────────────────────────────────────────────

class OpenAIAgentRunner:
    """
    Autonomous tool-calling agent loop using OpenAI.

    1. Send system_prompt + user message to GPT-4o.
    2. If the model returns tool_calls -> execute them, feed results back.
    3. Repeat until the model emits a text response or max_steps is reached.
    """

    def __init__(
        self,
        *,
        name: str = "agent",
        description: str = "",
        system_prompt: str = "You are a helpful AI assistant.",
        max_steps: int = 10,
        tools: ToolManager | None = None,
        llm: OpenAILLMClient | None = None,
    ):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.tools = tools or ToolManager()
        self.llm = llm or OpenAILLMClient()

    def _tools_to_openai_format(self) -> List[dict] | None:
        """Convert ToolManager tools to OpenAI function-calling format."""
        anthropic_tools = self.tools.to_anthropic_tools()
        if not anthropic_tools:
            return None
        openai_tools = []
        for t in anthropic_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            })
        return openai_tools

    async def run(self, user_message: str) -> str:
        """
        Execute the full agent loop for a single user message.

        Returns the final text response from the LLM.
        """
        messages: List[dict] = [
            {"role": "user", "content": user_message},
        ]

        openai_tools = self._tools_to_openai_format()

        for step in range(self.max_steps):
            logger.debug("[%s] step %d/%d", self.name, step + 1, self.max_steps)

            response = await self.llm.chat(
                messages,
                tools=openai_tools,
                system=self.system_prompt,
            )

            choice = response.choices[0]
            message = choice.message

            # If the model wants to call tools
            if message.tool_calls:
                # Append the assistant message (with tool_calls)
                messages.append(message.model_dump())

                for tool_call in message.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args_str = tool_call.function.arguments
                    logger.info("[%s] calling tool: %s", self.name, fn_name)

                    try:
                        fn_args = json.loads(fn_args_str) if fn_args_str else {}
                    except json.JSONDecodeError:
                        fn_args = {}

                    result = await self.tools.call(fn_name, fn_args)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                continue

            # Text response — done
            if message.content:
                logger.debug("[%s] final text response", self.name)
                return message.content

            # No content and no tool calls
            return ""

        logger.warning("[%s] max steps (%d) reached", self.name, self.max_steps)
        return "I've reached my step limit. Please try rephrasing your request."
