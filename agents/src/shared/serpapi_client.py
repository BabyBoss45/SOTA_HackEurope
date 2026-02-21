"""
SerpAPI Client — Async wrapper for Google Shopping, Flights, Hotels, Local search.

Graceful degradation: if ``SERPAPI_API_KEY`` is not set, ``from_env()``
returns ``None`` and callers fall back to LLM-based mocks.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

CURRENCY_MAP = {"GBP": "uk", "EUR": "de", "USD": "us"}


class SerpAPIClient:
    """Thin async wrapper around the ``serpapi`` package."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    @classmethod
    def from_env(cls) -> Optional["SerpAPIClient"]:
        key = os.getenv("SERPAPI_API_KEY", "").strip()
        if not key:
            logger.info("SERPAPI_API_KEY not set — SerpAPI integration disabled")
            return None
        return cls(api_key=key)

    def _search(self, params: dict[str, Any]) -> dict:
        """Run a blocking SerpAPI search (called in executor)."""
        from serpapi import GoogleSearch  # type: ignore

        params["api_key"] = self._api_key
        return GoogleSearch(params).get_dict()

    async def _async_search(self, params: dict[str, Any]) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search, params)

    # ── Google Shopping ──────────────────────────────────────

    async def shopping(
        self,
        query: str,
        *,
        max_price: float | None = None,
        currency: str = "GBP",
    ) -> list[dict]:
        gl = CURRENCY_MAP.get(currency.upper(), "uk")
        params: dict[str, Any] = {
            "engine": "google_shopping",
            "q": query,
            "gl": gl,
            "hl": "en",
        }
        if max_price:
            params["tbs"] = f"mr:1,price:1,ppr_max:{int(max_price)}"

        try:
            data = await self._async_search(params)
            results = data.get("shopping_results", [])
            return [
                {
                    "retailer": r.get("source", ""),
                    "product_name": r.get("title", ""),
                    "price": r.get("extracted_price", 0),
                    "currency": currency,
                    "url": r.get("link", r.get("product_link", "")),
                    "in_stock": True,
                    "stock_level": "unknown",
                    "delivery_days": None,
                    "rating": r.get("rating"),
                    "reviews_count": r.get("reviews"),
                    "thumbnail": r.get("thumbnail", ""),
                    "condition": "new",
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("SerpAPI shopping search failed: %s", e)
            return []

    # ── Google Flights ───────────────────────────────────────

    async def flights(
        self,
        departure: str,
        arrival: str,
        date: str,
        *,
        return_date: str | None = None,
        passengers: int = 1,
        currency: str = "GBP",
    ) -> list[dict]:
        params: dict[str, Any] = {
            "engine": "google_flights",
            "departure_id": departure,
            "arrival_id": arrival,
            "outbound_date": date,
            "adults": passengers,
            "currency": currency.upper(),
            "hl": "en",
            "type": "1" if not return_date else "1",
        }
        if return_date:
            params["return_date"] = return_date
            params["type"] = "1"

        try:
            data = await self._async_search(params)

            flights_out = []
            for bucket in ("best_flights", "other_flights"):
                for flight in data.get(bucket, []):
                    legs = flight.get("flights", [{}])
                    first_leg = legs[0] if legs else {}
                    last_leg = legs[-1] if legs else {}
                    flights_out.append({
                        "airline": first_leg.get("airline", ""),
                        "departure_time": first_leg.get("departure_airport", {}).get("time", ""),
                        "arrival_time": last_leg.get("arrival_airport", {}).get("time", ""),
                        "price_pp": flight.get("price", 0),
                        "total_price": flight.get("price", 0) * passengers,
                        "duration": f"{flight.get('total_duration', 0)}m",
                        "stops": len(legs) - 1,
                        "booking_url": f"https://www.google.com/travel/flights?q={departure}+to+{arrival}+{date}",
                        "airline_logo": first_leg.get("airline_logo", ""),
                    })
            return flights_out

        except Exception as e:
            logger.warning("SerpAPI flights search failed: %s", e)
            return []

    # ── Google Hotels ────────────────────────────────────────

    async def hotels(
        self,
        location: str,
        checkin: str,
        checkout: str,
        *,
        guests: int = 2,
        currency: str = "GBP",
    ) -> list[dict]:
        params: dict[str, Any] = {
            "engine": "google_hotels",
            "q": f"hotels in {location}",
            "check_in_date": checkin,
            "check_out_date": checkout,
            "adults": guests,
            "currency": currency.upper(),
            "hl": "en",
            "gl": CURRENCY_MAP.get(currency.upper(), "uk"),
        }

        try:
            data = await self._async_search(params)
            results = data.get("properties", [])
            return [
                {
                    "name": h.get("name", ""),
                    "type": "hotel",
                    "price_per_night": h.get("rate_per_night", {}).get("extracted_lowest", 0),
                    "total_price": h.get("total_rate", {}).get("extracted_lowest", 0),
                    "rating": h.get("overall_rating"),
                    "location": h.get("neighborhood", h.get("description", "")),
                    "amenities": h.get("amenities", [])[:6],
                    "booking_url": h.get("link", ""),
                    "thumbnail": h.get("images", [{}])[0].get("thumbnail", "") if h.get("images") else "",
                }
                for h in results
            ]
        except Exception as e:
            logger.warning("SerpAPI hotels search failed: %s", e)
            return []

    # ── Google Local / Maps (restaurants, POIs) ──────────────

    async def local(
        self,
        query: str,
        location: str,
        *,
        type_filter: str = "",
    ) -> list[dict]:
        params: dict[str, Any] = {
            "engine": "google_local",
            "q": f"{query} {type_filter}".strip() if type_filter else query,
            "location": location,
            "hl": "en",
        }

        try:
            data = await self._async_search(params)
            results = data.get("local_results", [])
            return [
                {
                    "name": r.get("title", ""),
                    "address": r.get("address", ""),
                    "rating": r.get("rating"),
                    "reviews_count": r.get("reviews"),
                    "cuisine": r.get("type", ""),
                    "price_range": r.get("price", ""),
                    "phone": r.get("phone", ""),
                    "website": r.get("website", ""),
                    "hours": r.get("hours", ""),
                    "thumbnail": r.get("thumbnail", ""),
                    "description": r.get("description", ""),
                    "gps_coordinates": r.get("gps_coordinates", {}),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("SerpAPI local search failed: %s", e)
            return []
