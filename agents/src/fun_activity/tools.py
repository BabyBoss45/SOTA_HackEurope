"""
Fun Activity Agent Tools

Tools for discovering local events (concerts, workshops, exhibitions, comedy, fitness, etc.)
with preference learning and weather-aware recommendations.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from pydantic import Field

from ..shared.tool_base import BaseTool

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-5-20241022"

# In-memory event preference history (can be extended to DB/Mem0)
_event_history: dict[str, list[dict]] = {}


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _extract_json_array(raw: str) -> list[dict]:
    """Extract JSON array from LLM response, handling markdown fences."""
    text = raw.strip()
    for start in ["[", "```json\n[", "```\n["]:
        if text.startswith(start):
            text = text[len(start):]
            break
    for end in ["]", "]\n```", "]"]:
        if text.rstrip().endswith(end):
            text = text[: text.rstrip().rfind(end) + 1]
            break
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []


class SearchLocalEventsTool(BaseTool):
    """
    Search for local events: concerts, workshops, exhibitions, pop-ups,
    talks, fitness classes, comedy nights, hackathons.
    """

    name: str = "search_local_events"
    description: str = """
    Search for fun local events matching the user's criteria.
    Returns concerts, workshops, exhibitions, pop-ups, talks, fitness classes,
    comedy nights, hackathons. Use Eventbrite, Ticketmaster, Meetup, Luma, Dice, Fever.
    Only return future events. Include direct URLs to event pages.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City or region (e.g. London, Paris, Berlin)",
            },
            "date_from": {
                "type": "string",
                "description": "Start date YYYY-MM-DD (default: today)",
            },
            "date_to": {
                "type": "string",
                "description": "End date YYYY-MM-DD (default: +14 days)",
            },
            "categories": {
                "type": "string",
                "description": "Comma-separated: concerts, workshops, exhibitions, comedy, fitness, talks, hackathons",
            },
            "max_budget": {
                "type": "number",
                "description": "Max price in local currency (optional)",
            },
        },
        "required": ["location"],
    }

    async def execute(
        self,
        location: str = "London",
        date_from: str | None = None,
        date_to: str | None = None,
        categories: str | None = None,
        max_budget: float | None = None,
    ) -> str:
        """Search for local events using Claude."""
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return json.dumps({
                "success": False,
                "error": "ANTHROPIC_API_KEY not set",
                "events": [],
            })

        today = datetime.utcnow()
        date_from = date_from or _today_str()
        if not date_to:
            date_to = (today + timedelta(days=14)).strftime("%Y-%m-%d")

        cat_clause = f" Focus on: {categories}." if categories else ""
        budget_clause = f" Prefer events under {max_budget}." if max_budget else ""

        prompt = (
            f"List fun local events in {location} between {date_from} and {date_to}.{cat_clause}{budget_clause}\n\n"
            f"Consider: Eventbrite, Ticketmaster, Meetup, Luma, Dice, Fever, local venues.\n"
            f"Today is {_today_str()}. ONLY include future events.\n\n"
            f"Return ONLY a JSON array (no markdown) where each element has:\n"
            f'{{"name": "...", "date": "YYYY-MM-DD", "time": "HH:MM", "venue": "...", '
            f'"url": "https://direct-event-link", "price": 0, "category": "concert|workshop|exhibition|comedy|fitness|talk|hackathon|other", '
            f'"description": "...", "indoor": true}}\n\n'
            f"If none found, return []."
        )

        try:
            client = AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=os.getenv("LLM_MODEL", CLAUDE_MODEL),
                system="You are an event discovery assistant. Return ONLY valid JSON arrays. Never include past events.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4096,
            )
            raw = resp.content[0].text if resp.content else "[]"
            events = _extract_json_array(raw)
            logger.info("search_local_events returned %d event(s)", len(events))
            return json.dumps({
                "success": True,
                "count": len(events),
                "events": events,
                "search_params": {"location": location, "date_from": date_from, "date_to": date_to},
            }, indent=2)
        except Exception as e:
            logger.error("search_local_events failed: %s", e)
            return json.dumps({"success": False, "error": str(e), "events": []})


class GetWeatherTool(BaseTool):
    """Get weather for a location to adapt indoor/outdoor recommendations."""

    name: str = "get_weather"
    description: str = "Get weather forecast for a location. Use for weather-aware event suggestions (e.g. push indoor if rain)."
    parameters: dict = {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name"},
            "date": {"type": "string", "description": "YYYY-MM-DD (optional)"},
        },
        "required": ["location"],
    }

    async def execute(self, location: str = "London", date: str | None = None) -> str:
        """Get weather — uses OpenWeatherMap if key set, else returns neutral."""
        api_key = os.getenv("OPENWEATHER_API_KEY")
        if api_key:
            try:
                import httpx
                city = location.split(",")[0].strip()
                url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
                async with httpx.AsyncClient() as client:
                    r = await client.get(url, timeout=10)
                    if r.status_code == 200:
                        d = r.json()
                        main = d.get("main", {})
                        weather = d.get("weather", [{}])[0]
                        condition = weather.get("main", "").lower()
                        indoor = "rain" in condition or "snow" in condition
                        return json.dumps({
                            "success": True,
                            "location": location,
                            "temp_c": main.get("temp"),
                            "condition": condition,
                            "indoor_recommended": indoor,
                        })
            except Exception as e:
                logger.debug("OpenWeatherMap failed: %s", e)
        return json.dumps({
            "success": True,
            "location": location,
            "indoor_recommended": False,
            "note": "Weather unknown — consider both indoor and outdoor options.",
        })


class PersistEventOutcomeTool(BaseTool):
    """Store event outcome for preference learning (attendance, rating, budget)."""

    name: str = "persist_event_outcome"
    description: str = """
    Record the outcome of an event the user attended or considered.
    Use after user selects an event. Stores: event_type, budget, attendance, group_size, rating_inferred.
    This helps the agent learn preferences over time.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID (default: default)"},
            "event_type": {"type": "string", "description": "e.g. indie_concert, comedy, workshop"},
            "budget": {"type": "number", "description": "Price paid or considered"},
            "attendance": {"type": "boolean", "description": "Did user attend?"},
            "group_size": {"type": "integer", "description": "Number of people"},
            "rating_inferred": {"type": "number", "description": "0-1 inferred satisfaction"},
        },
        "required": ["event_type"],
    }

    async def execute(
        self,
        user_id: str = "default",
        event_type: str = "",
        budget: float | None = None,
        attendance: bool = True,
        group_size: int | None = None,
        rating_inferred: float | None = None,
    ) -> str:
        """Persist event outcome for learning."""
        record = {
            "event_type": event_type,
            "budget": budget,
            "attendance": attendance,
            "group_size": group_size,
            "rating_inferred": rating_inferred,
            "timestamp": datetime.utcnow().isoformat(),
        }
        _event_history.setdefault(user_id, []).append(record)
        if len(_event_history[user_id]) > 50:
            _event_history[user_id] = _event_history[user_id][-50:]
        return json.dumps({"success": True, "message": "Outcome recorded", "record": record})


class GetEventPreferencesTool(BaseTool):
    """Retrieve learned event preferences for the user."""

    name: str = "get_event_preferences"
    description: str = "Get the user's learned event preferences from past attendance and ratings."
    parameters: dict = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID (default: default)"},
        },
        "required": [],
    }

    async def execute(self, user_id: str = "default") -> str:
        """Return event history and inferred preferences."""
        history = _event_history.get(user_id, [])
        if not history:
            return json.dumps({
                "success": True,
                "preferences": {},
                "event_history": [],
                "note": "No event history yet. Use general recommendations.",
            })
        budgets = [h["budget"] for h in history if h.get("budget") is not None]
        types = [h["event_type"] for h in history if h.get("event_type")]
        return json.dumps({
            "success": True,
            "preferences": {
                "budget_ceiling": max(budgets) if budgets else None,
                "liked_types": list(set(types)),
                "event_count": len(history),
            },
            "event_history": history[-10:],
        }, indent=2)


def create_fun_activity_tools() -> list[BaseTool]:
    """Create all Fun Activity agent tools."""
    return [
        SearchLocalEventsTool(),
        GetWeatherTool(),
        PersistEventOutcomeTool(),
        GetEventPreferencesTool(),
    ]
