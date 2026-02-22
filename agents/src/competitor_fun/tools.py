"""
Competitor Fun Agent Tools — OpenAI Edition

Nightlife & adventure discovery tools. Competes with the Claude-based
Fun Activity Agent by offering edgier, more spontaneous recommendations
powered by GPT-4o.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from ..shared.tool_base import BaseTool

logger = logging.getLogger(__name__)

OPENAI_MODEL = "gpt-4o"

# In-memory adventure preference history
_adventure_history: dict[str, list[dict]] = {}


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


class SearchNightlifeEventsTool(BaseTool):
    """
    Search for nightlife and adventure events: clubs, rooftop bars,
    live DJ sets, underground parties, late-night food tours, karaoke,
    escape rooms, secret cinema, pub crawls.
    """

    name: str = "search_nightlife_events"
    description: str = """
    Search for nightlife and adventure events in a city.
    Returns clubs, rooftop bars, live DJ sets, underground parties,
    late-night food tours, karaoke nights, escape rooms, secret cinema, pub crawls.
    Focuses on after-dark and high-energy experiences.
    Uses Eventbrite, Dice, Fever, Resident Advisor, Time Out, local venues.
    Only return future events. Include direct URLs.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City or region (e.g. London, Berlin, Amsterdam)",
            },
            "date_from": {
                "type": "string",
                "description": "Start date YYYY-MM-DD (default: today)",
            },
            "date_to": {
                "type": "string",
                "description": "End date YYYY-MM-DD (default: +7 days)",
            },
            "vibe": {
                "type": "string",
                "description": "Vibe filter: chill, wild, underground, fancy, quirky, spontaneous",
            },
            "max_budget": {
                "type": "number",
                "description": "Max price in local currency (optional)",
            },
            "group_size": {
                "type": "integer",
                "description": "Number of people going (affects venue suggestions)",
            },
        },
        "required": ["location"],
    }

    async def execute(
        self,
        location: str = "London",
        date_from: str | None = None,
        date_to: str | None = None,
        vibe: str | None = None,
        max_budget: float | None = None,
        group_size: int | None = None,
    ) -> str:
        """Search for nightlife events using OpenAI GPT-4o."""
        from openai import AsyncOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return json.dumps({
                "success": False,
                "error": "OPENAI_API_KEY not set",
                "events": [],
            })

        today = datetime.utcnow()
        date_from = date_from or _today_str()
        if not date_to:
            date_to = (today + timedelta(days=7)).strftime("%Y-%m-%d")

        vibe_clause = f" Vibe: {vibe}." if vibe else ""
        budget_clause = f" Prefer events under {max_budget}." if max_budget else ""
        group_clause = f" Group of {group_size} people." if group_size else ""

        prompt = (
            f"List exciting nightlife and adventure events in {location} between {date_from} and {date_to}."
            f"{vibe_clause}{budget_clause}{group_clause}\n\n"
            f"Consider: Resident Advisor, Dice, Fever, Time Out, Eventbrite, local venue listings.\n"
            f"Focus on: clubs, rooftop bars, live DJ sets, underground parties, late-night food tours, "
            f"karaoke, escape rooms, secret cinema, pub crawls, comedy, immersive experiences.\n"
            f"Today is {_today_str()}. ONLY include future events.\n\n"
            f"Return ONLY a JSON array (no markdown) where each element has:\n"
            f'{{"name": "...", "date": "YYYY-MM-DD", "time": "HH:MM", "venue": "...", '
            f'"url": "https://direct-event-link", "price": 0, '
            f'"category": "club|rooftop|dj_set|underground|food_tour|karaoke|escape_room|secret_cinema|pub_crawl|comedy|immersive|other", '
            f'"description": "...", "indoor": true, "vibe_score": 8}}\n\n'
            f"vibe_score is 1-10 (10 = most exciting/adventurous).\n"
            f"If none found, return []."
        )

        try:
            client = AsyncOpenAI(api_key=api_key)
            resp = await client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", OPENAI_MODEL),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a nightlife and adventure discovery assistant. "
                            "Return ONLY valid JSON arrays. Never include past events. "
                            "Prioritize exciting, unique, and spontaneous experiences."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=4096,
            )
            raw = resp.choices[0].message.content or "[]"
            events = _extract_json_array(raw)
            logger.info("search_nightlife_events returned %d event(s)", len(events))
            return json.dumps({
                "success": True,
                "count": len(events),
                "events": events,
                "search_params": {
                    "location": location,
                    "date_from": date_from,
                    "date_to": date_to,
                    "vibe": vibe,
                },
            }, indent=2)
        except Exception as e:
            logger.error("search_nightlife_events failed: %s", e)
            return json.dumps({"success": False, "error": str(e), "events": []})


class GetVibeCheckTool(BaseTool):
    """Get real-time vibe check for a location — crowd energy, weather, trending spots."""

    name: str = "get_vibe_check"
    description: str = (
        "Get a real-time vibe check for a city. Returns weather, crowd energy prediction, "
        "trending neighbourhoods, and whether it's a good night to go out."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name"},
            "date": {"type": "string", "description": "YYYY-MM-DD (optional, default: today)"},
        },
        "required": ["location"],
    }

    async def execute(self, location: str = "London", date: str | None = None) -> str:
        """Get vibe check — weather + crowd energy."""
        # Weather check
        weather_data = {"condition": "unknown", "temp_c": None, "indoor_recommended": False}
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
                        weather_data = {
                            "condition": condition,
                            "temp_c": main.get("temp"),
                            "indoor_recommended": "rain" in condition or "snow" in condition,
                        }
            except Exception as e:
                logger.debug("OpenWeatherMap failed: %s", e)

        # Day-of-week energy prediction
        target_date = date or _today_str()
        try:
            day_of_week = datetime.strptime(target_date, "%Y-%m-%d").strftime("%A")
        except ValueError:
            day_of_week = "Unknown"

        energy_map = {
            "Monday": 3, "Tuesday": 4, "Wednesday": 5,
            "Thursday": 7, "Friday": 9, "Saturday": 10, "Sunday": 6,
        }
        crowd_energy = energy_map.get(day_of_week, 5)

        return json.dumps({
            "success": True,
            "location": location,
            "date": target_date,
            "day_of_week": day_of_week,
            "weather": weather_data,
            "crowd_energy": crowd_energy,
            "go_out_score": min(10, crowd_energy + (2 if not weather_data["indoor_recommended"] else -1)),
            "recommendation": (
                "Perfect night to go out!" if crowd_energy >= 8
                else "Decent night — look for something special." if crowd_energy >= 5
                else "Chill night — maybe a cozy bar or escape room?"
            ),
        }, indent=2)


class TrackAdventureOutcomeTool(BaseTool):
    """Record adventure outcome for preference learning."""

    name: str = "track_adventure_outcome"
    description: str = (
        "Record the outcome of a nightlife/adventure experience. "
        "Tracks vibe preference, budget, group dynamics, and satisfaction "
        "to improve future recommendations."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID (default: default)"},
            "adventure_type": {"type": "string", "description": "e.g. club_night, rooftop_bar, escape_room, pub_crawl"},
            "vibe": {"type": "string", "description": "User's vibe: chill, wild, underground, fancy, quirky"},
            "budget_spent": {"type": "number", "description": "Amount spent"},
            "group_size": {"type": "integer", "description": "Number of people"},
            "satisfaction": {"type": "number", "description": "0-10 satisfaction score"},
            "would_repeat": {"type": "boolean", "description": "Would the user do this again?"},
        },
        "required": ["adventure_type"],
    }

    async def execute(
        self,
        user_id: str = "default",
        adventure_type: str = "",
        vibe: str | None = None,
        budget_spent: float | None = None,
        group_size: int | None = None,
        satisfaction: float | None = None,
        would_repeat: bool = True,
    ) -> str:
        """Persist adventure outcome."""
        record = {
            "adventure_type": adventure_type,
            "vibe": vibe,
            "budget_spent": budget_spent,
            "group_size": group_size,
            "satisfaction": satisfaction,
            "would_repeat": would_repeat,
            "timestamp": datetime.utcnow().isoformat(),
        }
        _adventure_history.setdefault(user_id, []).append(record)
        if len(_adventure_history[user_id]) > 50:
            _adventure_history[user_id] = _adventure_history[user_id][-50:]
        return json.dumps({"success": True, "message": "Adventure logged!", "record": record})


class GetAdventureProfileTool(BaseTool):
    """Retrieve learned adventure preferences."""

    name: str = "get_adventure_profile"
    description: str = "Get the user's adventure profile: preferred vibes, budget range, favourite types, group preferences."
    parameters: dict = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID (default: default)"},
        },
        "required": [],
    }

    async def execute(self, user_id: str = "default") -> str:
        """Return adventure history and inferred profile."""
        history = _adventure_history.get(user_id, [])
        if not history:
            return json.dumps({
                "success": True,
                "profile": {},
                "adventure_history": [],
                "note": "No adventure history yet. Go bold with recommendations!",
            })
        budgets = [h["budget_spent"] for h in history if h.get("budget_spent") is not None]
        vibes = [h["vibe"] for h in history if h.get("vibe")]
        types = [h["adventure_type"] for h in history if h.get("adventure_type")]
        scores = [h["satisfaction"] for h in history if h.get("satisfaction") is not None]
        return json.dumps({
            "success": True,
            "profile": {
                "avg_budget": sum(budgets) / len(budgets) if budgets else None,
                "max_budget": max(budgets) if budgets else None,
                "preferred_vibes": list(set(vibes)),
                "favourite_types": list(set(types)),
                "avg_satisfaction": round(sum(scores) / len(scores), 1) if scores else None,
                "total_adventures": len(history),
            },
            "adventure_history": history[-10:],
        }, indent=2)


def create_competitor_fun_tools() -> list[BaseTool]:
    """Create all Competitor Fun (Nightlife & Adventure) agent tools."""
    return [
        SearchNightlifeEventsTool(),
        GetVibeCheckTool(),
        TrackAdventureOutcomeTool(),
        GetAdventureProfileTool(),
    ]
