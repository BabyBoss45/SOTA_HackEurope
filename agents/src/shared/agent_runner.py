"""
Agent Runner — Anthropic-powered tool-calling agent loop.

Uses the Anthropic Messages API with Claude for LLM interactions.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic

from .tool_base import ToolManager

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  LLM Client
# ──────────────────────────────────────────────────────────────

class LLMClient:
    """
    Thin wrapper around ``anthropic.AsyncAnthropic`` for chat completions
    with tool-calling support.
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        api_key: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = AsyncAnthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    async def chat(
        self,
        messages: List[dict],
        tools: List[dict] | None = None,
        system: str | None = None,
    ) -> Any:
        """
        Send a messages request and return the raw response.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)
        return response


# ──────────────────────────────────────────────────────────────
#  AgentRunner
# ──────────────────────────────────────────────────────────────

class AgentRunner:
    """
    Autonomous tool-calling agent loop.

    1. Send ``system_prompt`` + user message to the LLM.
    2. If the LLM returns tool_use blocks → execute them, feed results back.
    3. Repeat until the LLM emits a text response or ``max_steps`` is reached.
    """

    def __init__(
        self,
        *,
        name: str = "agent",
        description: str = "",
        system_prompt: str = "You are a helpful AI assistant.",
        next_step_prompt: str = "",
        max_steps: int = 10,
        tools: ToolManager | None = None,
        llm: LLMClient | None = None,
    ):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.next_step_prompt = next_step_prompt
        self.max_steps = max_steps
        self.tools = tools or ToolManager()
        self.llm = llm or LLMClient()

    async def run(self, user_message: str) -> str:
        """
        Execute the full agent loop for a single user message.

        Returns the final text response from the LLM.
        """
        messages: List[dict] = [
            {"role": "user", "content": user_message},
        ]

        anthropic_tools = self.tools.to_anthropic_tools() or None

        for step in range(self.max_steps):
            logger.debug("[%s] step %d/%d", self.name, step + 1, self.max_steps)

            response = await self.llm.chat(
                messages,
                tools=anthropic_tools,
                system=self.system_prompt,
            )

            # ── Check for tool use ────────────────────────
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            # ── Text response with no tool calls → done ───
            if text_blocks and not tool_use_blocks:
                logger.debug("[%s] final text response", self.name)
                return text_blocks[0].text

            # ── Tool calls → execute each ─────────────────
            if tool_use_blocks:
                # Append the assistant message as-is
                messages.append({"role": "assistant", "content": response.content})

                # Build tool results
                tool_results = []
                for tool_block in tool_use_blocks:
                    fn_name = tool_block.name
                    fn_args = tool_block.input
                    logger.info("[%s] calling tool: %s", self.name, fn_name)

                    result = await self.tools.call(fn_name, fn_args)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result,
                    })

                messages.append({"role": "user", "content": tool_results})
                continue

            # ── No content and no tool calls → done ───────
            if text_blocks:
                return text_blocks[0].text
            return ""

        logger.warning("[%s] max steps (%d) reached", self.name, self.max_steps)
        return "I've reached my step limit. Please try rephrasing your request."

    async def run_with_history(
        self,
        user_message: str,
        history: List[dict],
    ) -> dict:
        """
        Like :meth:`run` but accepts a pre-existing conversation history.
        The system prompt is passed separately via the ``system`` parameter.

        Returns a dict with:
          - "response": str — the final text from the LLM
          - "tool_results": list[dict] — raw results from each tool call
        """
        messages: List[dict] = []

        # Filter out any system messages from history (Anthropic uses separate system param)
        for msg in history:
            if msg.get("role") != "system":
                messages.append(msg)

        messages.append({"role": "user", "content": user_message})

        anthropic_tools = self.tools.to_anthropic_tools() or None
        tool_results: List[dict] = []

        for step in range(self.max_steps):
            response = await self.llm.chat(
                messages,
                tools=anthropic_tools,
                system=self.system_prompt,
            )

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if text_blocks and not tool_use_blocks:
                text = text_blocks[0].text
                logger.info("[%s] step %d → text response (len=%d)", self.name, step+1, len(text))
                return {"response": text, "tool_results": tool_results}

            if tool_use_blocks:
                messages.append({"role": "assistant", "content": response.content})

                results_for_message = []
                for tool_block in tool_use_blocks:
                    fn_name = tool_block.name
                    logger.info("[%s] step %d → tool call: %s", self.name, step+1, fn_name)
                    print(f"[{self.name}] calling tool: {fn_name}")
                    result = await self.tools.call(fn_name, tool_block.input)
                    tool_results.append({"tool": fn_name, "result": result})
                    results_for_message.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result,
                    })
                messages.append({"role": "user", "content": results_for_message})
                continue

            text = text_blocks[0].text if text_blocks else ""
            return {"response": text, "tool_results": tool_results}

        return {"response": "I've reached my step limit. Please try rephrasing your request.", "tool_results": tool_results}
