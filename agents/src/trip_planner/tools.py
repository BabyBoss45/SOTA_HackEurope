"""
Group Trip Planner Agent Tools

Tools for inferring trip parameters from user profile, searching flights
and accommodation, building itineraries, and sharing with group members.
Key differentiator: confidence scoring to minimize friction.
Uses SerpAPI for real flights/hotels, Mem0 for persistent user profiles,
Twilio for group notifications, with graceful fallbacks.
"""

import os
import json
import logging
import random
from typing import Any
from datetime import datetime, timezone, timedelta
from collections import Counter

from ..shared.tool_base import BaseTool

logger = logging.getLogger(__name__)

_travel_profiles: dict[str, dict] = {
    "default": {
        "home_city": "London",
        "preferred_airport": "LHR",
        "budget_history": [150, 200, 180, 160, 220],
        "past_trips": [
            {"destination": "Barcelona", "group": ["Alex", "Sam", "Jordan"], "budget_pp": 180},
            {"destination": "Amsterdam", "group": ["Alex", "Sam"], "budget_pp": 150},
            {"destination": "Prague", "group": ["Alex", "Sam", "Jordan", "Taylor"], "budget_pp": 120},
        ],
        "preferred_airlines": ["easyJet", "Ryanair", "BA"],
        "travel_style": "mid-range",
        "preferred_accommodation": "Airbnb",
    },
}

_trip_history: dict[str, list[dict]] = {}


class InferFromProfileTool(BaseTool):
    """Infer trip parameters from user profile with confidence scores."""

    name: str = "infer_from_profile"
    description: str = """
    Analyze the user's travel profile and history to infer missing trip
    parameters. Returns each parameter with a confidence score (0.0-1.0).
    Only parameters with confidence < 0.6 need to be asked.
    This minimizes the number of questions the user needs to answer.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User ID to look up travel profile",
            },
            "destination": {
                "type": "string",
                "description": "Stated destination (if any)",
            },
            "group_size": {
                "type": "integer",
                "description": "Stated group size (if any)",
            },
            "date_hint": {
                "type": "string",
                "description": "Any date hint from the user (e.g. 'next month', 'March')",
            },
            "budget_hint": {
                "type": "string",
                "description": "Any budget hint (e.g. 'cheap', '200 per person')",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        user_id: str = "default",
        destination: str = "",
        group_size: int = 0,
        date_hint: str = "",
        budget_hint: str = "",
    ) -> str:
        profile = await self._load_profile(user_id)
        past_trips = profile.get("past_trips", [])

        inferences = {}

        home = profile.get("home_city", "")
        if home:
            inferences["departure_city"] = {"value": home, "confidence": 0.95, "source": "user_profile"}
        else:
            inferences["departure_city"] = {"value": None, "confidence": 0.0, "source": "unknown"}

        budget_history = profile.get("budget_history", [])
        if budget_hint:
            try:
                budget_val = float("".join(c for c in budget_hint if c.isdigit() or c == "."))
                inferences["budget_per_person"] = {"value": budget_val, "confidence": 0.90, "source": "user_stated"}
            except (ValueError, TypeError):
                if "cheap" in budget_hint.lower():
                    inferences["budget_per_person"] = {"value": 100, "confidence": 0.65, "source": "inferred_from_hint"}
                elif "luxury" in budget_hint.lower():
                    inferences["budget_per_person"] = {"value": 400, "confidence": 0.65, "source": "inferred_from_hint"}
                else:
                    avg = sum(budget_history) / len(budget_history) if budget_history else 150
                    inferences["budget_per_person"] = {"value": round(avg), "confidence": 0.50, "source": "history_average"}
        elif budget_history:
            avg = sum(budget_history) / len(budget_history)
            inferences["budget_per_person"] = {"value": round(avg), "confidence": 0.68, "source": "history_average"}
        else:
            inferences["budget_per_person"] = {"value": 150, "confidence": 0.30, "source": "default"}

        if group_size > 0:
            matching_groups = [t["group"] for t in past_trips if len(t["group"]) == group_size - 1]
            if matching_groups:
                inferences["group_members"] = {"value": matching_groups[0], "confidence": 0.82, "source": "past_trip_match"}
            else:
                all_companions: list[str] = []
                for t in past_trips:
                    all_companions.extend(t.get("group", []))
                if all_companions:
                    top = Counter(all_companions).most_common(group_size - 1)
                    inferences["group_members"] = {"value": [name for name, _ in top], "confidence": 0.60, "source": "frequent_companions"}
                else:
                    inferences["group_members"] = {"value": None, "confidence": 0.0, "source": "unknown"}
        else:
            if past_trips:
                sizes = [len(t.get("group", [])) + 1 for t in past_trips]
                avg_size = round(sum(sizes) / len(sizes))
                inferences["group_members"] = {"value": f"~{avg_size} people (based on past trips)", "confidence": 0.45, "source": "history_average"}
            else:
                inferences["group_members"] = {"value": None, "confidence": 0.0, "source": "unknown"}

        if date_hint:
            now = datetime.now(timezone.utc)
            hint_lower = date_hint.lower()
            if "next month" in hint_lower:
                next_month = now.replace(day=1) + timedelta(days=32)
                next_month = next_month.replace(day=1)
                inferences["date_range"] = {
                    "value": f"{next_month.strftime('%Y-%m-01')} to {next_month.strftime('%Y-%m-28')}",
                    "confidence": 0.44,
                    "source": "partial_hint",
                    "needs_clarification": "Which specific dates or weekend next month?",
                }
            elif "weekend" in hint_lower:
                days_until_friday = (4 - now.weekday()) % 7
                if days_until_friday == 0:
                    days_until_friday = 7
                friday = now + timedelta(days=days_until_friday)
                inferences["date_range"] = {
                    "value": f"{friday.strftime('%Y-%m-%d')} to {(friday + timedelta(days=2)).strftime('%Y-%m-%d')}",
                    "confidence": 0.55,
                    "source": "weekend_inference",
                }
            else:
                inferences["date_range"] = {"value": date_hint, "confidence": 0.70, "source": "user_stated"}
        else:
            inferences["date_range"] = {"value": None, "confidence": 0.0, "source": "unknown", "needs_clarification": "When would you like to go?"}

        if destination:
            inferences["destination"] = {"value": destination, "confidence": 0.95, "source": "user_stated"}

        style = profile.get("travel_style", "mid-range")
        inferences["travel_style"] = {"value": style, "confidence": 0.75, "source": "profile"}

        accom = profile.get("preferred_accommodation", "hotel")
        inferences["accommodation_preference"] = {"value": accom, "confidence": 0.70, "source": "profile"}

        needs_asking = []
        for field, data in inferences.items():
            if data["confidence"] < 0.6:
                question = data.get("needs_clarification", f"Could you confirm the {field.replace('_', ' ')}?")
                needs_asking.append({"field": field, "question": question, "confidence": data["confidence"]})

        return json.dumps({
            "success": True,
            "inferences": inferences,
            "needs_asking": needs_asking,
            "auto_filled_count": sum(1 for d in inferences.values() if d["confidence"] >= 0.6),
            "needs_clarification_count": len(needs_asking),
        }, indent=2)

    async def _load_profile(self, user_id: str) -> dict:
        """Try Mem0 first, fall back to in-memory profile."""
        from ..shared.mem0_client import Mem0Preferences

        mem0 = Mem0Preferences.from_env()
        if mem0:
            try:
                memories = await mem0.recall(user_id, "travel preferences home city budget trips")
                if memories:
                    profile: dict[str, Any] = {}
                    for m in memories:
                        text = m.get("memory", "")
                        if "home" in text.lower() or "city" in text.lower():
                            for city in ["London", "Manchester", "Birmingham", "Edinburgh", "Paris", "Berlin"]:
                                if city.lower() in text.lower():
                                    profile["home_city"] = city
                                    break
                        if "budget" in text.lower():
                            import re
                            nums = re.findall(r"\d+", text)
                            if nums:
                                profile.setdefault("budget_history", []).append(int(nums[0]))
                        if "airbnb" in text.lower():
                            profile["preferred_accommodation"] = "Airbnb"
                        elif "hotel" in text.lower():
                            profile["preferred_accommodation"] = "hotel"
                    if profile:
                        fallback = _travel_profiles.get(user_id, _travel_profiles.get("default", {}))
                        merged = {**fallback, **profile}
                        return merged
            except Exception as e:
                logger.debug("Mem0 profile load failed: %s", e)

        return _travel_profiles.get(user_id, _travel_profiles.get("default", {}))


class SearchFlightsTool(BaseTool):
    """Search for flight options between cities."""

    name: str = "search_flights"
    description: str = """
    Search for flights between departure and destination cities.
    Returns available options with prices, airlines, and times.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "departure_city": {
                "type": "string",
                "description": "City or airport to depart from",
            },
            "destination": {
                "type": "string",
                "description": "Destination city or airport",
            },
            "date_outbound": {
                "type": "string",
                "description": "Outbound flight date (YYYY-MM-DD)",
            },
            "date_return": {
                "type": "string",
                "description": "Return flight date (YYYY-MM-DD)",
            },
            "passengers": {
                "type": "integer",
                "description": "Number of passengers",
            },
            "max_price_pp": {
                "type": "number",
                "description": "Max price per person for flights",
            },
        },
        "required": ["departure_city", "destination"],
    }

    async def execute(
        self,
        departure_city: str,
        destination: str,
        date_outbound: str = "",
        date_return: str = "",
        passengers: int = 1,
        max_price_pp: float = 0.0,
    ) -> str:
        from ..shared.serpapi_client import SerpAPIClient

        serpapi = SerpAPIClient.from_env()
        flights: list[dict] = []
        source = "serpapi"

        if serpapi and date_outbound:
            flights = await serpapi.flights(
                departure=departure_city,
                arrival=destination,
                date=date_outbound,
                return_date=date_return or None,
                passengers=passengers,
            )

        if not flights:
            source = "llm_fallback"
            flights = await self._llm_search(departure_city, destination, date_outbound, date_return, passengers, max_price_pp)

        flights.sort(key=lambda x: x.get("price_pp", float("inf")))

        return json.dumps({
            "success": True,
            "source": source,
            "count": len(flights),
            "flights": flights,
            "route": f"{departure_city} -> {destination}",
        }, indent=2)

    async def _llm_search(
        self, departure_city: str, destination: str, date_outbound: str,
        date_return: str, passengers: int, max_price_pp: float,
    ) -> list[dict]:
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return []

        prompt = (
            f"Suggest 4 realistic flight options from {departure_city} to {destination}.\n"
            f"Dates: {date_outbound or 'flexible'} to {date_return or 'flexible'}\n"
            f"Passengers: {passengers}\n"
            + (f"Max price per person: {max_price_pp}\n" if max_price_pp else "")
            + f"\nReturn ONLY a JSON array where each element has:\n"
            f'{{"airline": "...", "departure_time": "HH:MM", "arrival_time": "HH:MM", '
            f'"price_pp": 89.99, "total_price": 179.98, "duration": "2h 30m", '
            f'"stops": 0, "booking_url": "https://..."}}\n\n'
            f"Use realistic prices for these routes."
        )

        try:
            client = AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022"),
                system="You are a flight search assistant. Return ONLY valid JSON arrays with realistic flight options.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2048,
            )
            raw = resp.content[0].text if resp.content else "[]"
            import re
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            return json.loads(raw) if raw.startswith("[") else []
        except Exception as e:
            logger.error("LLM flight search failed: %s", e)
            return []


class SearchAccommodationTool(BaseTool):
    """Search for accommodation options at the destination."""

    name: str = "search_accommodation"
    description: str = """
    Find hotels, Airbnbs, or hostels at the destination.
    Considers group size, budget, and accommodation preferences.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": "City to find accommodation in",
            },
            "check_in": {
                "type": "string",
                "description": "Check-in date (YYYY-MM-DD)",
            },
            "check_out": {
                "type": "string",
                "description": "Check-out date (YYYY-MM-DD)",
            },
            "guests": {
                "type": "integer",
                "description": "Number of guests",
            },
            "accommodation_type": {
                "type": "string",
                "description": "Preferred type: hotel, airbnb, hostel, any",
            },
            "max_price_per_night": {
                "type": "number",
                "description": "Max price per night total (not per person)",
            },
        },
        "required": ["destination"],
    }

    async def execute(
        self,
        destination: str,
        check_in: str = "",
        check_out: str = "",
        guests: int = 2,
        accommodation_type: str = "any",
        max_price_per_night: float = 0.0,
    ) -> str:
        from ..shared.serpapi_client import SerpAPIClient

        serpapi = SerpAPIClient.from_env()
        options: list[dict] = []
        source = "serpapi"

        if serpapi and check_in and check_out:
            options = await serpapi.hotels(
                location=destination,
                checkin=check_in,
                checkout=check_out,
                guests=guests,
            )

        if not options:
            source = "llm_fallback"
            options = await self._llm_search(destination, check_in, check_out, guests, accommodation_type, max_price_per_night)

        options.sort(key=lambda x: x.get("price_per_night", float("inf")))

        return json.dumps({
            "success": True,
            "source": source,
            "count": len(options),
            "accommodation": options,
            "destination": destination,
        }, indent=2)

    async def _llm_search(
        self, destination: str, check_in: str, check_out: str,
        guests: int, accommodation_type: str, max_price_per_night: float,
    ) -> list[dict]:
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return []

        prompt = (
            f"Suggest 4 accommodation options in {destination} for {guests} guests.\n"
            f"Dates: {check_in or 'flexible'} to {check_out or 'flexible'}\n"
            f"Type preference: {accommodation_type}\n"
            + (f"Max price per night: {max_price_per_night}\n" if max_price_per_night else "")
            + f"\nReturn ONLY a JSON array where each element has:\n"
            f'{{"name": "...", "type": "hotel|airbnb|hostel", "price_per_night": 120, '
            f'"total_price": 360, "rating": 4.5, "location": "neighborhood", '
            f'"amenities": ["wifi", "kitchen"], "booking_url": "https://..."}}\n\n'
            f"Use realistic names and prices for {destination}."
        )

        try:
            client = AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022"),
                system="You are an accommodation search assistant. Return ONLY valid JSON arrays.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2048,
            )
            raw = resp.content[0].text if resp.content else "[]"
            import re
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            return json.loads(raw) if raw.startswith("[") else []
        except Exception as e:
            logger.error("LLM accommodation search failed: %s", e)
            return []


class BuildItineraryTool(BaseTool):
    """Build a day-by-day trip itinerary, enriched with real POIs via SerpAPI."""

    name: str = "build_itinerary"
    description: str = """
    Create a day-by-day itinerary for the trip, including activities,
    restaurants, and sightseeing. Tailored to the group's interests.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": "Trip destination city",
            },
            "duration_days": {
                "type": "integer",
                "description": "Number of days for the trip",
            },
            "group_size": {
                "type": "integer",
                "description": "Number of people in the group",
            },
            "interests": {
                "type": "string",
                "description": "Group interests (e.g. 'food, nightlife, history, art')",
            },
            "budget_style": {
                "type": "string",
                "description": "Budget style: budget, mid-range, luxury",
            },
        },
        "required": ["destination", "duration_days"],
    }

    async def execute(
        self,
        destination: str,
        duration_days: int,
        group_size: int = 2,
        interests: str = "",
        budget_style: str = "mid-range",
    ) -> str:
        from ..shared.serpapi_client import SerpAPIClient

        real_pois: list[dict] = []
        serpapi = SerpAPIClient.from_env()
        if serpapi:
            try:
                real_pois = await serpapi.local(
                    query=f"things to do {interests}" if interests else "top attractions",
                    location=destination,
                )
            except Exception:
                pass

        poi_context = ""
        if real_pois:
            top = real_pois[:8]
            poi_context = "\n\nReal local places to consider incorporating:\n" + "\n".join(
                f"- {p['name']} ({p.get('rating', 'N/A')} stars, {p.get('cuisine', p.get('description', ''))})"
                for p in top
            )

        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return json.dumps({"success": False, "error": "ANTHROPIC_API_KEY not set"})

        prompt = (
            f"Create a {duration_days}-day itinerary for {group_size} people visiting {destination}.\n"
            f"Budget style: {budget_style}\n"
            f"Interests: {interests or 'general sightseeing, food, culture'}\n"
            f"{poi_context}\n\n"
            f"Return ONLY a JSON object with:\n"
            f'{{"destination": "{destination}", "duration_days": {duration_days}, '
            f'"days": [{{"day": 1, "title": "...", "activities": ['
            f'{{"time": "09:00", "activity": "...", "location": "...", "estimated_cost_pp": 0, "description": "..."}}]}}]}}\n\n'
            f"Include morning, afternoon, and evening activities for each day. "
            f"Include specific restaurant recommendations for lunch and dinner."
        )

        try:
            client = AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022"),
                system="You are a travel itinerary expert. Return ONLY valid JSON.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=4096,
            )
            raw = resp.content[0].text if resp.content else "{}"
            import re
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            itinerary = json.loads(raw) if raw.startswith("{") else {"raw": raw}

            return json.dumps({
                "success": True,
                "source": "llm" + ("_with_real_pois" if real_pois else ""),
                "itinerary": itinerary,
            }, indent=2)

        except Exception as e:
            logger.error("Itinerary building failed: %s", e)
            return json.dumps({"success": False, "error": str(e)})


class ShareWithGroupTool(BaseTool):
    """Share the trip plan with group members via Twilio SMS or simulated notification."""

    name: str = "share_with_group"
    description: str = """
    Share the trip itinerary and booking details with group members.
    Sends real SMS if Twilio is configured, otherwise simulates notifications.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "group_members": {
                "type": "string",
                "description": "Comma-separated list of group member names (or phone numbers for SMS)",
            },
            "trip_summary": {
                "type": "string",
                "description": "Summary of the trip plan to share",
            },
            "destination": {
                "type": "string",
                "description": "Trip destination",
            },
            "dates": {
                "type": "string",
                "description": "Trip dates",
            },
        },
        "required": ["group_members", "trip_summary"],
    }

    async def execute(
        self,
        group_members: str,
        trip_summary: str,
        destination: str = "",
        dates: str = "",
    ) -> str:
        members = [m.strip() for m in group_members.split(",") if m.strip()]

        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        twilio_phone = os.getenv("TWILIO_PHONE_NUMBER", "").strip()

        notifications = []
        sms_sent = 0

        for member in members:
            is_phone = member.startswith("+") and member[1:].replace(" ", "").isdigit()

            if is_phone and twilio_sid and twilio_token and twilio_phone:
                try:
                    from twilio.rest import Client  # type: ignore
                    twilio_client = Client(twilio_sid, twilio_token)
                    msg_body = f"Trip to {destination or 'TBD'}!\n{dates or ''}\n\n{trip_summary[:300]}"
                    twilio_client.messages.create(
                        body=msg_body,
                        from_=twilio_phone,
                        to=member,
                    )
                    notifications.append({"member": member, "status": "sent", "channel": "sms"})
                    sms_sent += 1
                except Exception as e:
                    logger.warning("Twilio SMS to %s failed: %s", member, e)
                    notifications.append({"member": member, "status": "failed", "channel": "sms", "error": str(e)})
            else:
                notifications.append({"member": member, "status": "sent", "channel": "app_notification"})

        return json.dumps({
            "success": True,
            "notifications_sent": len(notifications),
            "sms_sent": sms_sent,
            "members_notified": notifications,
            "message": f"Trip plan for {destination or 'the trip'} shared with {len(members)} group members.",
        }, indent=2)


def create_trip_planner_tools() -> list[BaseTool]:
    """Create all trip planner tools."""
    return [
        InferFromProfileTool(),
        SearchFlightsTool(),
        SearchAccommodationTool(),
        BuildItineraryTool(),
        ShareWithGroupTool(),
    ]
