"""
Smart Shopper Agent Tools

Tools for searching retailers, tracking price history, analyzing market
conditions, setting price alerts, and executing purchases.
Uses SerpAPI for real product search, Firestore for persistent storage,
with graceful fallback to LLM mocks.
"""

import os
import json
import logging
import random
from typing import Any
from datetime import datetime, timezone, timedelta

from ..shared.tool_base import BaseTool

logger = logging.getLogger(__name__)

_price_history: dict[str, list[dict]] = {}
_price_alerts: dict[str, list[dict]] = {}
_purchase_history: dict[str, list[dict]] = {}


async def _get_firestore():
    """Return Firestore Database instance, or None if unavailable."""
    try:
        from ..shared.database_firestore import Database
        return await Database.connect()
    except Exception:
        return None


class SearchRetailersTool(BaseTool):
    """Search multiple retailers for a product and compare prices."""

    name: str = "search_retailers"
    description: str = """
    Search across multiple online retailers for a specific product.
    Returns prices, availability, and links from different stores.
    Compares to find the best current deal.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "product_query": {
                "type": "string",
                "description": "What to search for (e.g. 'MacBook Air M3 256GB')",
            },
            "max_budget": {
                "type": "number",
                "description": "Maximum price in the specified currency",
            },
            "currency": {
                "type": "string",
                "description": "Currency code (GBP, EUR, USD). Default GBP",
            },
            "preferred_retailers": {
                "type": "string",
                "description": "Comma-separated preferred retailers (e.g. 'Amazon, John Lewis, Currys')",
            },
        },
        "required": ["product_query"],
    }

    async def execute(
        self,
        product_query: str,
        max_budget: float = 0.0,
        currency: str = "GBP",
        preferred_retailers: str = "",
    ) -> str:
        from ..shared.serpapi_client import SerpAPIClient

        serpapi = SerpAPIClient.from_env()
        listings: list[dict] = []
        source = "serpapi"

        if serpapi:
            listings = await serpapi.shopping(
                product_query, max_price=max_budget or None, currency=currency,
            )

        if not listings:
            source = "llm_fallback"
            listings = await self._llm_search(product_query, max_budget, currency, preferred_retailers)

        if max_budget > 0:
            within_budget = [l for l in listings if l.get("price", float("inf")) <= max_budget]
            over_budget = [l for l in listings if l.get("price", float("inf")) > max_budget]
        else:
            within_budget = listings
            over_budget = []

        within_budget.sort(key=lambda x: x.get("price", float("inf")))

        product_key = product_query.lower().strip()
        await self._persist_prices(product_key, within_budget[:5])

        best = within_budget[0] if within_budget else None

        return json.dumps({
            "success": True,
            "source": source,
            "product_query": product_query,
            "count_within_budget": len(within_budget),
            "count_over_budget": len(over_budget),
            "best_deal": best,
            "all_listings": within_budget + over_budget[:2],
            "currency": currency,
        }, indent=2)

    async def _persist_prices(self, product_key: str, listings: list[dict]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        entries = [
            {"price": l.get("price"), "retailer": l.get("retailer"), "timestamp": now}
            for l in listings if l.get("price")
        ]

        if product_key not in _price_history:
            _price_history[product_key] = []
        _price_history[product_key].extend(entries)

        db = await _get_firestore()
        if db:
            try:
                for entry in entries:
                    await db._adb.collection("priceHistory").add({
                        "product_key": product_key,
                        **entry,
                    })
            except Exception as e:
                logger.debug("Firestore price persist failed: %s", e)

    async def _llm_search(
        self, product_query: str, max_budget: float, currency: str, preferred_retailers: str,
    ) -> list[dict]:
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return []

        budget_note = f"\nMaximum budget: {max_budget} {currency}" if max_budget else ""
        retailer_note = f"\nPreferred retailers: {preferred_retailers}" if preferred_retailers else ""

        prompt = (
            f"Search for '{product_query}' across major UK/EU online retailers.\n"
            f"{budget_note}{retailer_note}\n\n"
            f"Return ONLY a JSON array of available listings, each with:\n"
            f'{{"retailer": "...", "product_name": "exact product name", '
            f'"price": 999.99, "currency": "{currency}", '
            f'"url": "https://real-retailer-url/product", '
            f'"in_stock": true, "stock_level": "high|medium|low|unknown", '
            f'"delivery_days": 2, "rating": 4.5, '
            f'"condition": "new|refurbished|used"}}\n\n'
            f"Include at least 5 retailers. Use realistic prices and real retailer URLs."
        )

        try:
            client = AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022"),
                system="You are a price comparison expert. Return ONLY valid JSON arrays with realistic current prices from real retailers.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=3072,
            )
            raw = resp.content[0].text if resp.content else "[]"
            import re
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            return json.loads(raw) if raw.startswith("[") else []
        except Exception as e:
            logger.error("LLM retailer search failed: %s", e)
            return []


class TrackPriceHistoryTool(BaseTool):
    """View and analyze price history for a product."""

    name: str = "track_price_history"
    description: str = """
    Get the price history for a product across retailers.
    Shows price trends over time and calculates average, min, max prices.
    Useful for deciding whether to buy now or wait.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "product_query": {
                "type": "string",
                "description": "Product to look up price history for",
            },
        },
        "required": ["product_query"],
    }

    async def execute(self, product_query: str) -> str:
        product_key = product_query.lower().strip()
        history = await self._load_history(product_key)

        if not history:
            return json.dumps({
                "success": True,
                "product": product_query,
                "history_entries": 0,
                "message": "No price history available. Run search_retailers first to start tracking.",
            })

        prices = [h["price"] for h in history if h.get("price")]
        avg_price = sum(prices) / len(prices) if prices else 0
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0

        trend = "stable"
        if len(prices) >= 4:
            mid = len(prices) // 2
            first_half_avg = sum(prices[:mid]) / mid
            second_half_avg = sum(prices[mid:]) / (len(prices) - mid)
            if second_half_avg < first_half_avg * 0.95:
                trend = "decreasing"
            elif second_half_avg > first_half_avg * 1.05:
                trend = "increasing"

        return json.dumps({
            "success": True,
            "product": product_query,
            "history_entries": len(history),
            "price_stats": {
                "average": round(avg_price, 2),
                "minimum": round(min_price, 2),
                "maximum": round(max_price, 2),
                "current": round(prices[-1], 2) if prices else None,
            },
            "trend": trend,
            "recent_entries": history[-5:],
        }, indent=2)

    async def _load_history(self, product_key: str) -> list[dict]:
        db = await _get_firestore()
        if db:
            try:
                q = (
                    db._adb.collection("priceHistory")
                    .where("product_key", "==", product_key)
                    .order_by("timestamp")
                    .limit(100)
                )
                results = [snap.to_dict() async for snap in q.stream()]
                if results:
                    return results
            except Exception as e:
                logger.debug("Firestore price history load failed: %s", e)

        return _price_history.get(product_key, [])


class AnalyzeMarketTool(BaseTool):
    """Analyze market conditions and make a buy/wait recommendation."""

    name: str = "analyze_market"
    description: str = """
    Perform economic analysis on a product to recommend buy now vs wait.
    Considers: price trend, stock levels, urgency, expected savings
    vs risk of stockout. Returns a clear recommendation with reasoning.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "product_query": {
                "type": "string",
                "description": "Product being considered",
            },
            "current_best_price": {
                "type": "number",
                "description": "Current best price found",
            },
            "target_price": {
                "type": "number",
                "description": "User's target price (max budget)",
            },
            "stock_level": {
                "type": "string",
                "description": "Current stock level: high, medium, low, unknown",
            },
            "urgency": {
                "type": "string",
                "description": "How urgently the user needs it: high, medium, low",
            },
        },
        "required": ["product_query", "current_best_price"],
    }

    async def execute(
        self,
        product_query: str,
        current_best_price: float,
        target_price: float = 0.0,
        stock_level: str = "unknown",
        urgency: str = "medium",
    ) -> str:
        product_key = product_query.lower().strip()
        history = await TrackPriceHistoryTool()._load_history(product_key)
        prices = [h["price"] for h in history if h.get("price")]

        trend = "stable"
        if len(prices) >= 4:
            mid = len(prices) // 2
            first_avg = sum(prices[:mid]) / mid
            second_avg = sum(prices[mid:]) / (len(prices) - mid)
            if second_avg < first_avg * 0.95:
                trend = "decreasing"
            elif second_avg > first_avg * 1.05:
                trend = "increasing"

        score = 50
        if target_price > 0:
            if current_best_price <= target_price:
                score += 20
            elif current_best_price <= target_price * 1.05:
                score += 10
            else:
                score -= 15

        stock_scores = {"low": 20, "medium": 5, "high": -5, "unknown": 0}
        score += stock_scores.get(stock_level.lower(), 0)

        if trend == "decreasing":
            score -= 15
        elif trend == "increasing":
            score += 15

        urgency_scores = {"high": 20, "medium": 5, "low": -10}
        score += urgency_scores.get(urgency.lower(), 0)

        if score >= 65:
            recommendation = "BUY NOW"
            reasoning = "Strong buy signal."
        elif score >= 45:
            recommendation = "CONSIDER BUYING"
            reasoning = "Reasonable time to buy, but waiting could yield small savings."
        elif score >= 30:
            recommendation = "WAIT"
            reasoning = "Price may drop further. Set an alert instead."
        else:
            recommendation = "WAIT AND MONITOR"
            reasoning = "Conditions favor waiting. Price trend is favorable for buyers."

        factors = []
        if trend == "decreasing":
            factors.append("Price is trending down")
        elif trend == "increasing":
            factors.append("Price is trending up -- act soon")
        if stock_level.lower() == "low":
            factors.append("Stock is low -- risk of selling out")
        if target_price and current_best_price <= target_price:
            factors.append(f"Price is within your budget of {target_price}")
        elif target_price:
            factors.append(f"Price is {current_best_price - target_price:.2f} over your target")

        return json.dumps({
            "success": True,
            "recommendation": recommendation,
            "confidence_score": min(max(score, 0), 100),
            "reasoning": reasoning,
            "factors": factors,
            "analysis": {
                "current_price": current_best_price,
                "target_price": target_price,
                "trend": trend,
                "stock_level": stock_level,
                "urgency": urgency,
            },
        }, indent=2)


class SetPriceAlertTool(BaseTool):
    """Set an alert for when a product drops below a target price."""

    name: str = "set_price_alert"
    description: str = """
    Register a price alert. When the product drops below the target price,
    the user will be notified. Returns alert confirmation.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "product_query": {
                "type": "string",
                "description": "Product to monitor",
            },
            "target_price": {
                "type": "number",
                "description": "Alert when price drops below this",
            },
            "currency": {
                "type": "string",
                "description": "Currency (default GBP)",
            },
            "user_id": {
                "type": "string",
                "description": "User ID for the alert",
            },
        },
        "required": ["product_query", "target_price"],
    }

    async def execute(
        self,
        product_query: str,
        target_price: float,
        currency: str = "GBP",
        user_id: str = "default",
    ) -> str:
        alert_id = f"ALERT-{random.randint(10000, 99999)}"
        alert_doc = {
            "alert_id": alert_id,
            "product": product_query,
            "target_price": target_price,
            "currency": currency,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "triggered": False,
        }

        if user_id not in _price_alerts:
            _price_alerts[user_id] = []
        _price_alerts[user_id].append(alert_doc)

        db = await _get_firestore()
        if db:
            try:
                await db._adb.collection("priceAlerts").document(alert_id).set(alert_doc)
            except Exception as e:
                logger.debug("Firestore alert persist failed: %s", e)

        return json.dumps({
            "success": True,
            "alert_id": alert_id,
            "product": product_query,
            "target_price": target_price,
            "currency": currency,
            "message": f"Price alert set. You'll be notified when '{product_query}' drops below {target_price} {currency}.",
        }, indent=2)


class ExecutePurchaseTool(BaseTool):
    """Record a product recommendation and provide the purchase link to the user."""

    name: str = "execute_purchase"
    description: str = """
    Record a product recommendation for the user. Does NOT make any real purchase.
    Returns the product URL so the user can buy it themselves if they choose.
    Records the recommendation in history for future reference.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "product_name": {
                "type": "string",
                "description": "Exact product name to purchase",
            },
            "retailer": {
                "type": "string",
                "description": "Retailer to buy from",
            },
            "price": {
                "type": "number",
                "description": "Price at purchase",
            },
            "currency": {
                "type": "string",
                "description": "Currency (default GBP)",
            },
            "url": {
                "type": "string",
                "description": "Product URL for the purchase",
            },
            "user_id": {
                "type": "string",
                "description": "User ID",
            },
        },
        "required": ["product_name", "retailer", "price"],
    }

    async def execute(
        self,
        product_name: str,
        retailer: str,
        price: float,
        currency: str = "GBP",
        url: str = "",
        user_id: str = "default",
    ) -> str:
        order_id = f"ORD-{random.randint(100000, 999999)}"

        record = {
            "order_id": order_id,
            "product": product_name,
            "retailer": retailer,
            "price": price,
            "currency": currency,
            "url": url,
            "purchased_at": datetime.now(timezone.utc).isoformat(),
        }

        if user_id not in _purchase_history:
            _purchase_history[user_id] = []
        _purchase_history[user_id].append(record)

        db = await _get_firestore()
        if db:
            try:
                await db._adb.collection("purchaseHistory").document(order_id).set(
                    {"user_id": user_id, **record}
                )
            except Exception as e:
                logger.debug("Firestore purchase persist failed: %s", e)

        return json.dumps({
            "success": True,
            "recommendation_id": order_id,
            "product": product_name,
            "retailer": retailer,
            "price": price,
            "currency": currency,
            "url": url,
            "message": (
                f"Best deal found: {product_name} from {retailer} "
                f"for {price} {currency}.\n"
                f"Buy it here: {url}" if url else
                f"Best deal found: {product_name} from {retailer} for {price} {currency}."
            ),
        }, indent=2)


def create_smart_shopper_tools() -> list[BaseTool]:
    """Create all smart shopper tools."""
    return [
        SearchRetailersTool(),
        TrackPriceHistoryTool(),
        AnalyzeMarketTool(),
        SetPriceAlertTool(),
        ExecutePurchaseTool(),
    ]
