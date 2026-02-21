"""
Gift Suggestion Agent Tools

Tools for analyzing recipients, searching gift options, and formatting
curated suggestions. Uses Mem0 for persistent recipient/preference memory,
SerpAPI for real product search, with graceful fallbacks.
"""

import os
import json
import logging
from typing import Any
from datetime import datetime, timezone

from ..shared.tool_base import BaseTool

logger = logging.getLogger(__name__)

_session_gifts: dict[str, list[dict]] = {}
_session_preferences: dict[str, dict] = {}


class AnalyzeRecipientTool(BaseTool):
    """Analyze a gift recipient using Mem0 memory or session fallback."""

    name: str = "analyze_recipient"
    description: str = """
    Look up what we know about a gift recipient: past gifts given to them,
    their interests, and the user's typical price comfort zone.
    Returns context to guide gift selection.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "recipient_name": {
                "type": "string",
                "description": "Name of the person receiving the gift",
            },
            "occasion": {
                "type": "string",
                "description": "Occasion for the gift (birthday, holiday, thank-you, etc.)",
            },
            "user_id": {
                "type": "string",
                "description": "User ID to look up gift history",
            },
        },
        "required": ["recipient_name"],
    }

    async def execute(
        self,
        recipient_name: str,
        occasion: str = "",
        user_id: str = "default",
    ) -> str:
        recipient_key = f"{user_id}:{recipient_name.lower().strip()}"

        past_gifts, prefs = await self._load_from_mem0(user_id, recipient_name)

        if not past_gifts:
            past_gifts = _session_gifts.get(recipient_key, [])
        if not prefs:
            prefs = _session_preferences.get(user_id, {})

        past_categories = [g.get("category", "") for g in past_gifts if g.get("category")]
        avg_budget = prefs.get("avg_budget", 30.0)
        min_budget = prefs.get("min_budget", 15.0)
        max_budget = prefs.get("max_budget", 75.0)

        budget_note = "default range (no history)"
        if prefs.get("gift_count", 0) > 0:
            budget_note = f"based on {prefs['gift_count']} past gifts"

        occasion_multiplier = 1.0
        if occasion:
            occ_lower = occasion.lower()
            if any(w in occ_lower for w in ["wedding", "milestone", "graduation"]):
                occasion_multiplier = 2.0
            elif any(w in occ_lower for w in ["birthday", "anniversary"]):
                occasion_multiplier = 1.3
            elif any(w in occ_lower for w in ["thank", "just because"]):
                occasion_multiplier = 0.8

        suggested_budget = round(avg_budget * occasion_multiplier, 2)

        return json.dumps({
            "success": True,
            "recipient": recipient_name,
            "occasion": occasion or "not specified",
            "past_gifts_count": len(past_gifts),
            "past_categories": past_categories[-5:],
            "avoid_categories": past_categories[-3:],
            "price_comfort_zone": {
                "min": min_budget,
                "avg": avg_budget,
                "max": max_budget,
                "note": budget_note,
            },
            "suggested_budget": suggested_budget,
            "occasion_multiplier": occasion_multiplier,
        }, indent=2)

    async def _load_from_mem0(self, user_id: str, recipient_name: str) -> tuple[list[dict], dict]:
        from ..shared.mem0_client import Mem0Preferences

        mem0 = Mem0Preferences.from_env()
        if not mem0:
            return [], {}

        past_gifts: list[dict] = []
        prefs: dict = {}

        try:
            memories = await mem0.recall(
                user_id,
                f"gifts for {recipient_name} past gift history preferences budget",
                category="gift_suggestion",
            )
            for m in memories:
                text = m.get("memory", "")
                if "gave" in text.lower() or "gift" in text.lower():
                    past_gifts.append({"description": text, "category": text.split()[-1] if text else ""})
                if "budget" in text.lower() or "price" in text.lower():
                    import re
                    nums = re.findall(r"[\d.]+", text)
                    if nums:
                        val = float(nums[0])
                        prefs.setdefault("min_budget", val)
                        prefs.setdefault("max_budget", val)
                        prefs["avg_budget"] = val
                        prefs["gift_count"] = prefs.get("gift_count", 0) + 1
        except Exception as e:
            logger.debug("Mem0 recipient load failed: %s", e)

        return past_gifts, prefs


class SearchGiftsTool(BaseTool):
    """Search for gift ideas using SerpAPI or LLM fallback."""

    name: str = "search_gifts"
    description: str = """
    Find gift options for a recipient within a budget range.
    Takes into account recipient interests, occasion, and categories to avoid.
    Returns a list of gift ideas with estimated prices and purchase links.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "recipient_name": {
                "type": "string",
                "description": "Who the gift is for",
            },
            "budget_min": {
                "type": "number",
                "description": "Minimum budget in user's currency (default 15)",
            },
            "budget_max": {
                "type": "number",
                "description": "Maximum budget in user's currency (default 75)",
            },
            "interests": {
                "type": "string",
                "description": "Comma-separated interests or hobbies of the recipient",
            },
            "occasion": {
                "type": "string",
                "description": "The occasion (birthday, holiday, etc.)",
            },
            "avoid_categories": {
                "type": "string",
                "description": "Comma-separated categories to avoid (e.g. recent past gifts)",
            },
        },
        "required": ["recipient_name"],
    }

    async def execute(
        self,
        recipient_name: str,
        budget_min: float = 15.0,
        budget_max: float = 75.0,
        interests: str = "",
        occasion: str = "",
        avoid_categories: str = "",
    ) -> str:
        from ..shared.serpapi_client import SerpAPIClient

        serpapi = SerpAPIClient.from_env()
        gifts: list[dict] = []
        source = "serpapi"

        if serpapi and interests:
            query = f"gift {interests} {occasion}".strip()
            raw_results = await serpapi.shopping(query, max_price=budget_max, currency="GBP")
            for r in raw_results:
                price = r.get("price", 0)
                if budget_min <= price <= budget_max * 1.1:
                    gifts.append({
                        "name": r.get("product_name", r.get("retailer", "Gift")),
                        "category": interests.split(",")[0].strip() if interests else "general",
                        "estimated_price": price,
                        "description": f"From {r.get('retailer', 'online')}. Rating: {r.get('rating', 'N/A')}",
                        "purchase_url": r.get("url", ""),
                    })

        if not gifts:
            source = "llm_fallback"
            gifts = await self._llm_search(recipient_name, budget_min, budget_max, interests, occasion, avoid_categories)

        return json.dumps({
            "success": True,
            "source": source,
            "count": len(gifts),
            "gifts": gifts,
            "budget_range": {"min": budget_min, "max": budget_max},
        }, indent=2)

    async def _llm_search(
        self, recipient_name: str, budget_min: float, budget_max: float,
        interests: str, occasion: str, avoid_categories: str,
    ) -> list[dict]:
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return []

        avoid_note = ""
        if avoid_categories:
            avoid_note = f"\nAVOID these categories (recently gifted): {avoid_categories}"

        prompt = (
            f"Suggest exactly 5 thoughtful gift ideas for someone named {recipient_name}.\n"
            f"Budget: {budget_min}-{budget_max} GBP\n"
            f"Occasion: {occasion or 'general'}\n"
            f"Their interests: {interests or 'unknown'}\n"
            f"{avoid_note}\n\n"
            f"Return ONLY a JSON array where each element has:\n"
            f'{{"name": "...", "category": "...", "estimated_price": 29.99, '
            f'"description": "one sentence why this is a good pick", '
            f'"purchase_url": "https://amazon.co.uk/...or similar real retailer URL"}}\n\n'
            f"Be creative and specific. Include a mix of price points within the range."
        )

        try:
            client = AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022"),
                system="You are a gift recommendation expert. Return ONLY valid JSON arrays.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2048,
            )
            raw = resp.content[0].text if resp.content else "[]"
            import re
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            gifts = json.loads(raw) if raw.startswith("[") else []
            return [g for g in gifts if budget_min <= g.get("estimated_price", 0) <= budget_max * 1.1]
        except Exception as e:
            logger.error("LLM gift search failed: %s", e)
            return []


class FormatSuggestionsTool(BaseTool):
    """Format gift suggestions into a clean summary, picking the top 3."""

    name: str = "format_gift_suggestions"
    description: str = """
    Take a list of gift options and produce a clean, user-friendly summary
    of the top 3 picks with names, prices, descriptions, and links.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "gifts_json": {
                "type": "string",
                "description": "JSON string of the gifts array to format",
            },
            "recipient_name": {
                "type": "string",
                "description": "Name of the recipient for the summary header",
            },
        },
        "required": ["gifts_json"],
    }

    async def execute(self, gifts_json: str, recipient_name: str = "them") -> str:
        try:
            gifts = json.loads(gifts_json)
        except json.JSONDecodeError:
            return "Could not parse gift data."

        if not gifts:
            return "I couldn't find any gift ideas matching your criteria. Could you give me more details about their interests?"

        top = gifts[:3]
        lines = [f"Here are 3 gift ideas for {recipient_name}:\n"]
        for i, g in enumerate(top, 1):
            name = g.get("name", "Gift idea")
            price = g.get("estimated_price", "?")
            desc = g.get("description", "")
            url = g.get("purchase_url", "")

            lines.append(f"{i}. {name} (~{price} GBP)")
            if desc:
                lines.append(f"   {desc}")
            if url:
                lines.append(f"   {url}")
            lines.append("")

        lines.append("Would you like me to find more options or go ahead with one of these?")
        return "\n".join(lines)


class RecordGiftChoiceTool(BaseTool):
    """Record a gift choice to Mem0 and session for future suggestions."""

    name: str = "record_gift_choice"
    description: str = """
    Record that the user chose a specific gift. This builds history
    so future suggestions avoid repetition and match the user's price range.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "recipient_name": {
                "type": "string",
                "description": "Who the gift is for",
            },
            "gift_name": {
                "type": "string",
                "description": "Name of the chosen gift",
            },
            "category": {
                "type": "string",
                "description": "Gift category (e.g. 'books', 'electronics', 'experience')",
            },
            "price": {
                "type": "number",
                "description": "Price of the gift",
            },
            "user_id": {
                "type": "string",
                "description": "User ID for tracking",
            },
        },
        "required": ["recipient_name", "gift_name"],
    }

    async def execute(
        self,
        recipient_name: str,
        gift_name: str,
        category: str = "",
        price: float = 0.0,
        user_id: str = "default",
    ) -> str:
        recipient_key = f"{user_id}:{recipient_name.lower().strip()}"

        if recipient_key not in _session_gifts:
            _session_gifts[recipient_key] = []
        _session_gifts[recipient_key].append({
            "gift_name": gift_name,
            "category": category,
            "price": price,
            "date": datetime.now(timezone.utc).isoformat(),
        })

        if price > 0:
            if user_id not in _session_preferences:
                _session_preferences[user_id] = {
                    "total_spend": 0.0, "gift_count": 0,
                    "min_budget": price, "max_budget": price, "avg_budget": price,
                }
            prefs = _session_preferences[user_id]
            prefs["total_spend"] += price
            prefs["gift_count"] += 1
            prefs["avg_budget"] = round(prefs["total_spend"] / prefs["gift_count"], 2)
            prefs["min_budget"] = min(prefs["min_budget"], price)
            prefs["max_budget"] = max(prefs["max_budget"], price)

        from ..shared.mem0_client import Mem0Preferences

        mem0 = Mem0Preferences.from_env()
        if mem0:
            try:
                content = f"User gave {gift_name} ({category}) to {recipient_name} for {price} GBP"
                await mem0.remember(user_id, content, category="gift_suggestion", metadata={
                    "recipient": recipient_name, "gift": gift_name, "category": category, "price": price,
                })
            except Exception as e:
                logger.debug("Mem0 gift record failed: %s", e)

        return json.dumps({
            "success": True,
            "recorded": {
                "recipient": recipient_name,
                "gift": gift_name,
                "category": category,
                "price": price,
            },
        })


def create_gift_suggestion_tools() -> list[BaseTool]:
    """Create all gift suggestion tools."""
    return [
        AnalyzeRecipientTool(),
        SearchGiftsTool(),
        FormatSuggestionsTool(),
        RecordGiftChoiceTool(),
    ]
