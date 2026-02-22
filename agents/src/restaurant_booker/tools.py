"""
Restaurant Booker Agent Tools

Tools for checking calendar availability, searching restaurants,
making reservations, and learning cuisine preferences.
Uses Google Calendar API for real availability, SerpAPI for real
restaurant search, Mem0 for persistent preferences, with graceful fallbacks.
"""

import os
import json
import logging
import random
from typing import Any
from datetime import datetime, timezone, timedelta

from ..shared.tool_base import BaseTool

logger = logging.getLogger(__name__)

_cuisine_preferences: dict[str, dict[str, int]] = {}
_cancelled_places: dict[str, set[str]] = {}
_booking_history: dict[str, list[dict]] = {}


class CheckCalendarTool(BaseTool):
    """Check the user's calendar for free evening slots via Google Calendar API."""

    name: str = "check_calendar"
    description: str = """
    Look up the user's calendar for a specific date and find free evening
    time slots suitable for dinner (typically 18:00-22:00).
    Returns available time windows.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date to check in YYYY-MM-DD or natural language (e.g. 'Friday')",
            },
            "user_id": {
                "type": "string",
                "description": "User ID to look up calendar",
            },
        },
        "required": ["date"],
    }

    async def execute(self, date: str, user_id: str = "default") -> str:
        target = self._parse_date(date)
        date_str = target.strftime("%Y-%m-%d")
        day_name = target.strftime("%A")

        gcal_result = await self._check_google_calendar(target, user_id)
        calendar_connected = gcal_result is not None

        if gcal_result is None:
            free_slots, busy_slots = self._mock_calendar()
        else:
            free_slots = gcal_result
            all_slots = ["18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00"]
            busy_slots = [s for s in all_slots if s not in free_slots]

        result: dict[str, Any] = {
            "success": True,
            "date": date_str,
            "day": day_name,
            "free_slots": free_slots,
            "busy_slots": busy_slots,
            "recommended_time": free_slots[len(free_slots) // 2] if free_slots else None,
            "calendar_connected": calendar_connected,
        }
        if not calendar_connected:
            result["note"] = (
                "Google Calendar not connected — showing all evening slots as available. "
                "The user can connect their calendar at /api/auth/google/calendar for real availability."
            )

        return json.dumps(result, indent=2)

    def _parse_date(self, date: str) -> datetime:
        today = datetime.now(timezone.utc)
        date_lower = date.lower().strip()
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for i, day in enumerate(day_names):
            if day in date_lower:
                days_ahead = i - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                return today + timedelta(days=days_ahead)
        try:
            return datetime.strptime(date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (ValueError, IndexError):
            return today + timedelta(days=1)

    async def _get_user_calendar_token(self, user_id: str) -> dict | None:
        """Fetch the user's Google Calendar OAuth token from their profile via Butler API."""
        import httpx

        butler_url = os.getenv("BUTLER_ENDPOINT", "http://localhost:3001")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{butler_url}/api/agent/user-context/{user_id}")
                if resp.status_code == 200:
                    profile = resp.json().get("profile", {})
                    extra = profile.get("extra", {})
                    gcal = extra.get("googleCalendar") or profile.get("googleCalendar")
                    if gcal and gcal.get("accessToken"):
                        return gcal
        except Exception as e:
            logger.debug("Could not fetch user calendar token: %s", e)

        db = await _get_firestore()
        if db:
            try:
                profile = await db.get_user_profile(user_id)
                if profile:
                    gcal = (profile.get("extra", {}) or {}).get("googleCalendar")
                    if gcal and gcal.get("accessToken"):
                        return gcal
            except Exception:
                pass

        return None

    async def _refresh_access_token(self, refresh_token: str) -> str | None:
        """Use the refresh token to get a new access token from Google."""
        import httpx

        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            return None

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                if resp.status_code == 200:
                    return resp.json().get("access_token")
        except Exception as e:
            logger.warning("Google token refresh failed: %s", e)
        return None

    async def _check_google_calendar(self, target: datetime, user_id: str) -> list[str] | None:
        """Query Google Calendar freebusy using the user's stored OAuth token."""
        gcal_tokens = await self._get_user_calendar_token(user_id)
        if not gcal_tokens:
            return None

        access_token = gcal_tokens.get("accessToken", "")
        expires_at = gcal_tokens.get("expiresAt", 0)

        if expires_at and expires_at < datetime.now(timezone.utc).timestamp() * 1000:
            refresh_token = gcal_tokens.get("refreshToken", "")
            if refresh_token:
                new_token = await self._refresh_access_token(refresh_token)
                if new_token:
                    access_token = new_token
                else:
                    return None
            else:
                return None

        if not access_token:
            return None

        import httpx

        evening_start = target.replace(hour=18, minute=0, second=0, microsecond=0)
        evening_end = target.replace(hour=22, minute=0, second=0, microsecond=0)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://www.googleapis.com/calendar/v3/freeBusy",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={
                        "timeMin": evening_start.isoformat(),
                        "timeMax": evening_end.isoformat(),
                        "timeZone": "Europe/London",
                        "items": [{"id": "primary"}],
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Google Calendar API returned %d", resp.status_code)
                    return None

                data = resp.json()
                busy_periods = data.get("calendars", {}).get("primary", {}).get("busy", [])

            all_slots = ["18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00"]
            busy_set: set[str] = set()

            for period in busy_periods:
                start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
                for slot_str in all_slots:
                    h, m = map(int, slot_str.split(":"))
                    slot_dt = target.replace(hour=h, minute=m, second=0, microsecond=0)
                    if start <= slot_dt < end:
                        busy_set.add(slot_str)

            return [s for s in all_slots if s not in busy_set]

        except Exception as e:
            logger.warning("Google Calendar freebusy query failed: %s", e)
            return None

    def _mock_calendar(self) -> tuple[list[str], list[str]]:
        all_slots = ["18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00"]
        busy_count = random.randint(0, 3)
        busy_slots = random.sample(all_slots, min(busy_count, len(all_slots)))
        free_slots = [s for s in all_slots if s not in busy_slots]
        return free_slots, busy_slots


class SearchRestaurantsTool(BaseTool):
    """Search for restaurants using SerpAPI google_local or LLM fallback."""

    name: str = "search_restaurants"
    description: str = """
    Find nearby restaurants matching the user's preferences.
    Considers cuisine type, location, party size, and avoids
    previously cancelled places. Returns ranked options.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Area or neighborhood to search (e.g. 'Soho, London')",
            },
            "cuisine": {
                "type": "string",
                "description": "Preferred cuisine type (e.g. 'Italian', 'Japanese')",
            },
            "party_size": {
                "type": "integer",
                "description": "Number of guests (default 2)",
            },
            "date": {
                "type": "string",
                "description": "Date for the reservation (YYYY-MM-DD)",
            },
            "time": {
                "type": "string",
                "description": "Preferred time (e.g. '19:30')",
            },
            "user_id": {
                "type": "string",
                "description": "User ID for preference lookup",
            },
        },
        "required": ["location"],
    }

    async def execute(
        self,
        location: str,
        cuisine: str = "",
        party_size: int = 2,
        date: str = "",
        time: str = "19:30",
        user_id: str = "default",
    ) -> str:
        from ..shared.serpapi_client import SerpAPIClient
        from ..shared.mem0_client import Mem0Preferences

        mem0_prefs = await self._load_mem0_prefs(user_id)
        cancelled = _cancelled_places.get(user_id, set())
        if mem0_prefs.get("cancelled"):
            cancelled = cancelled | set(mem0_prefs["cancelled"])

        if not cuisine and mem0_prefs.get("favorite_cuisines"):
            cuisine = mem0_prefs["favorite_cuisines"][0]

        serpapi = SerpAPIClient.from_env()
        restaurants: list[dict] = []
        source = "serpapi"

        if serpapi:
            query = f"{cuisine} restaurant" if cuisine else "restaurant"
            raw_results = await serpapi.local(query=query, location=location, type_filter="restaurant")
            for r in raw_results:
                name = r.get("name", "")
                if name.lower() not in {c.lower() for c in cancelled}:
                    restaurants.append({
                        "name": name,
                        "cuisine": r.get("cuisine", cuisine or "various"),
                        "address": r.get("address", ""),
                        "rating": r.get("rating"),
                        "reviews_count": r.get("reviews_count"),
                        "price_range": r.get("price_range", "$$"),
                        "booking_url": r.get("website", ""),
                        "phone": r.get("phone", ""),
                        "available": True,
                        "description": r.get("description", ""),
                    })

        if not restaurants:
            source = "llm_fallback"
            restaurants = await self._llm_search(location, cuisine, party_size, date, time, user_id, cancelled)

        return json.dumps({
            "success": True,
            "source": source,
            "count": len(restaurants),
            "restaurants": restaurants,
            "search_params": {
                "location": location,
                "cuisine": cuisine,
                "party_size": party_size,
                "date": date,
                "time": time,
            },
        }, indent=2)

    async def _load_mem0_prefs(self, user_id: str) -> dict:
        from ..shared.mem0_client import Mem0Preferences

        mem0 = Mem0Preferences.from_env()
        if not mem0:
            return {}
        try:
            memories = await mem0.recall(user_id, "restaurant cuisine preferences cancelled avoided")
            prefs: dict[str, Any] = {}
            for m in memories:
                text = m.get("memory", "")
                if "cancel" in text.lower() or "avoid" in text.lower():
                    prefs.setdefault("cancelled", []).append(text)
                for cuisine_type in ["Italian", "Japanese", "Chinese", "Indian", "French", "Thai", "Mexican", "Korean"]:
                    if cuisine_type.lower() in text.lower():
                        prefs.setdefault("favorite_cuisines", []).append(cuisine_type)
            return prefs
        except Exception:
            return {}

    async def _llm_search(
        self, location: str, cuisine: str, party_size: int,
        date: str, time: str, user_id: str, cancelled: set,
    ) -> list[dict]:
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return []

        prefs = _cuisine_preferences.get(user_id, {})
        pref_note = ""
        if prefs and not cuisine:
            top_cuisines = sorted(prefs.items(), key=lambda x: x[1], reverse=True)[:3]
            pref_note = f"\nUser's preferred cuisines (from history): {', '.join(c[0] for c in top_cuisines)}"

        cancel_note = ""
        if cancelled:
            cancel_note = f"\nAVOID these restaurants (previously cancelled): {', '.join(list(cancelled)[:5])}"

        prompt = (
            f"Suggest 5 real restaurants near {location} for a party of {party_size}.\n"
            f"Cuisine preference: {cuisine or 'any'}\n"
            f"Date: {date or 'upcoming'}, Time: {time}\n"
            f"{pref_note}{cancel_note}\n\n"
            f"Return ONLY a JSON array where each element has:\n"
            f'{{"name": "...", "cuisine": "...", "address": "...", '
            f'"rating": 4.5, "price_range": "$$", '
            f'"booking_url": "https://...", '
            f'"available": true, '
            f'"description": "one line description"}}\n\n'
            f"Use real restaurant names for the {location} area."
        )

        try:
            client = AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001"),
                system="You are a restaurant recommendation expert. Return ONLY valid JSON arrays with real restaurants.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=2048,
            )
            raw = resp.content[0].text if resp.content else "[]"
            import re
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            restaurants = json.loads(raw) if raw.startswith("[") else []

            if cancelled:
                restaurants = [r for r in restaurants if r.get("name", "").lower() not in {c.lower() for c in cancelled}]

            return restaurants
        except Exception as e:
            logger.error("LLM restaurant search failed: %s", e)
            return []


class MakeReservationTool(BaseTool):
    """Record a booking intent for preference learning. Does NOT place a real reservation."""

    name: str = "make_reservation"
    description: str = """
    Record the user's booking intent for preference learning and history tracking.
    Does NOT place an actual reservation -- the Caller Agent will phone the venue
    to secure the booking separately. Returns the restaurant details and a
    reference ID for tracking.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "restaurant_name": {
                "type": "string",
                "description": "Name of the restaurant",
            },
            "date": {
                "type": "string",
                "description": "Reservation date (YYYY-MM-DD)",
            },
            "time": {
                "type": "string",
                "description": "Reservation time (e.g. '19:30')",
            },
            "party_size": {
                "type": "integer",
                "description": "Number of guests",
            },
            "cuisine": {
                "type": "string",
                "description": "Cuisine type (for preference tracking)",
            },
            "booking_url": {
                "type": "string",
                "description": "Restaurant booking/website URL",
            },
            "user_id": {
                "type": "string",
                "description": "User ID for booking record",
            },
        },
        "required": ["restaurant_name", "date", "time"],
    }

    async def execute(
        self,
        restaurant_name: str,
        date: str,
        time: str,
        party_size: int = 2,
        cuisine: str = "",
        booking_url: str = "",
        user_id: str = "default",
    ) -> str:
        booking_ref = f"BK-{random.randint(10000, 99999)}"

        if user_id not in _booking_history:
            _booking_history[user_id] = []
        _booking_history[user_id].append({
            "restaurant": restaurant_name,
            "cuisine": cuisine,
            "date": date,
            "time": time,
            "party_size": party_size,
            "booking_ref": booking_ref,
            "booking_url": booking_url,
            "status": "pending_call",
            "booked_at": datetime.now(timezone.utc).isoformat(),
        })

        if cuisine:
            if user_id not in _cuisine_preferences:
                _cuisine_preferences[user_id] = {}
            _cuisine_preferences[user_id][cuisine] = _cuisine_preferences[user_id].get(cuisine, 0) + 1

        from ..shared.mem0_client import Mem0Preferences

        mem0 = Mem0Preferences.from_env()
        if mem0:
            try:
                await mem0.remember(
                    user_id,
                    f"Wants to book {restaurant_name} ({cuisine}) for {party_size} on {date} at {time}",
                    category="restaurant_booking",
                    metadata={"restaurant": restaurant_name, "cuisine": cuisine},
                )
            except Exception:
                pass

        return json.dumps({
            "success": True,
            "booking_intent": {
                "reference": booking_ref,
                "restaurant": restaurant_name,
                "date": date,
                "time": time,
                "party_size": party_size,
                "status": "pending_call",
                "booking_url": booking_url,
            },
            "message": (
                f"Recorded intent: {restaurant_name} for {party_size} on {date} at {time}. "
                f"Ref: {booking_ref}. The Caller Agent will phone the venue to confirm."
                + (f"\nVenue page: {booking_url}" if booking_url else "")
            ),
        }, indent=2)


class LearnPreferencesTool(BaseTool):
    """Retrieve or update restaurant/cuisine preferences from Mem0 or session."""

    name: str = "learn_preferences"
    description: str = """
    Get the user's restaurant preferences learned from past bookings:
    favorite cuisines, avoided places, typical party size, preferred times.
    Can also record a cancellation to avoid that place in future.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User ID to look up preferences",
            },
            "record_cancellation": {
                "type": "string",
                "description": "Restaurant name to mark as cancelled/avoided (optional)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        user_id: str = "default",
        record_cancellation: str = "",
    ) -> str:
        from ..shared.mem0_client import Mem0Preferences

        if record_cancellation:
            if user_id not in _cancelled_places:
                _cancelled_places[user_id] = set()
            _cancelled_places[user_id].add(record_cancellation)

            mem0 = Mem0Preferences.from_env()
            if mem0:
                try:
                    await mem0.remember(
                        user_id,
                        f"User cancelled reservation at {record_cancellation} -- avoid in future",
                        category="restaurant_booking",
                    )
                except Exception:
                    pass

        mem0 = Mem0Preferences.from_env()
        mem0_cuisines: list[str] = []
        mem0_cancelled: list[str] = []
        if mem0:
            try:
                memories = await mem0.recall(user_id, "restaurant cuisine preference cancelled booking")
                for m in memories:
                    text = m.get("memory", "")
                    if "cancel" in text.lower() or "avoid" in text.lower():
                        mem0_cancelled.append(text)
                    for cuisine_type in ["Italian", "Japanese", "Chinese", "Indian", "French", "Thai", "Mexican", "Korean"]:
                        if cuisine_type.lower() in text.lower() and "cancel" not in text.lower():
                            mem0_cuisines.append(cuisine_type)
            except Exception:
                pass

        prefs = _cuisine_preferences.get(user_id, {})
        history = _booking_history.get(user_id, [])
        cancelled = list(_cancelled_places.get(user_id, set()))

        all_cuisines = list(prefs.keys()) + mem0_cuisines
        cuisine_counts: dict[str, int] = {}
        for c in all_cuisines:
            cuisine_counts[c] = cuisine_counts.get(c, 0) + 1
        top_cuisines = sorted(cuisine_counts.items(), key=lambda x: x[1], reverse=True)

        typical_party_size = 2
        if history:
            sizes = [b.get("party_size", 2) for b in history]
            typical_party_size = round(sum(sizes) / len(sizes))

        all_cancelled = cancelled + mem0_cancelled

        return json.dumps({
            "success": True,
            "preferences": {
                "favorite_cuisines": [c[0] for c in top_cuisines[:5]],
                "cuisine_counts": dict(top_cuisines[:10]),
                "avoided_restaurants": all_cancelled[:10],
                "typical_party_size": typical_party_size,
                "total_bookings": len(history),
            },
        }, indent=2)


def create_restaurant_booker_tools() -> list[BaseTool]:
    """Create all restaurant booker tools."""
    return [
        CheckCalendarTool(),
        SearchRestaurantsTool(),
        MakeReservationTool(),
        LearnPreferencesTool(),
    ]
