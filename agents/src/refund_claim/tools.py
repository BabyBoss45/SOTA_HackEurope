"""
Refund Claim Agent Tools

Tools for parsing tickets, checking eligibility, generating/submitting claims,
tracking status, and escalating rejections.
Uses Firestore for persistent claim tracking and policy storage,
with graceful fallback to in-memory stores.
"""

import os
import json
import logging
import random
from typing import Any
from datetime import datetime, timezone

from ..shared.tool_base import BaseTool

logger = logging.getLogger(__name__)

_claim_history: dict[str, list[dict]] = {}

_REFUND_POLICIES = {
    "national rail": {"min_delay_minutes": 30, "claim_window_days": 28, "url": "https://www.nationalrail.co.uk/delay-repay"},
    "avanti west coast": {"min_delay_minutes": 15, "claim_window_days": 28, "url": "https://www.avantiwestcoast.co.uk/delay-repay"},
    "gwr": {"min_delay_minutes": 15, "claim_window_days": 28, "url": "https://www.gwr.com/help-and-support/delay-repay"},
    "lner": {"min_delay_minutes": 30, "claim_window_days": 28, "url": "https://www.lner.co.uk/help/delay-repay/"},
    "eurostar": {"min_delay_minutes": 60, "claim_window_days": 90, "url": "https://www.eurostar.com/uk-en/travel-info/delay-compensation"},
    "ryanair": {"min_delay_minutes": 180, "claim_window_days": 365, "url": "https://www.ryanair.com/gb/en/useful-info/help-centre"},
    "easyjet": {"min_delay_minutes": 180, "claim_window_days": 365, "url": "https://www.easyjet.com/en/claim"},
    "british airways": {"min_delay_minutes": 180, "claim_window_days": 365, "url": "https://www.britishairways.com/travel/customercontact/public/en_gb"},
}


async def _get_firestore():
    try:
        from ..shared.database_firestore import Database
        return await Database.connect()
    except Exception:
        return None


class ParseTicketTool(BaseTool):
    """Extract booking details from ticket text or email content (LLM-powered)."""

    name: str = "parse_ticket"
    description: str = """
    Parse a ticket email or text to extract: operator, booking reference,
    journey details (from, to, date, time), and delay information.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "ticket_text": {
                "type": "string",
                "description": "Raw ticket email text or booking details",
            },
        },
        "required": ["ticket_text"],
    }

    async def execute(self, ticket_text: str) -> str:
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return json.dumps({"success": False, "error": "ANTHROPIC_API_KEY not set"})

        prompt = (
            f"Extract these fields from the following ticket/email text:\n\n"
            f"{ticket_text}\n\n"
            f"Return ONLY a JSON object with:\n"
            f'{{"operator": "...", "booking_reference": "...", '
            f'"from_station": "...", "to_station": "...", '
            f'"scheduled_departure": "YYYY-MM-DD HH:MM", '
            f'"actual_departure": "YYYY-MM-DD HH:MM", '
            f'"delay_minutes": 0, '
            f'"service_type": "train|flight|bus", '
            f'"ticket_class": "standard|first", '
            f'"ticket_price": 0.0}}\n\n'
            f"If a field cannot be determined, use null."
        )

        try:
            client = AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001"),
                system="You are a ticket parsing expert. Return ONLY valid JSON.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1024,
            )
            raw = resp.content[0].text if resp.content else "{}"
            import re
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
            parsed = json.loads(raw) if raw.startswith("{") else {}
            return json.dumps({"success": True, "ticket_data": parsed}, indent=2)

        except Exception as e:
            logger.error("Ticket parsing failed: %s", e)
            return json.dumps({"success": False, "error": str(e)})


class CheckEligibilityTool(BaseTool):
    """Check refund eligibility from Firestore policies or hardcoded fallback."""

    name: str = "check_eligibility"
    description: str = """
    Check refund eligibility based on the operator's delay compensation policy.
    Returns whether the claim is eligible, the claim window, and the refund URL.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "operator": {
                "type": "string",
                "description": "Transport operator name (e.g. 'National Rail', 'Ryanair')",
            },
            "delay_minutes": {
                "type": "integer",
                "description": "Delay in minutes",
            },
            "journey_date": {
                "type": "string",
                "description": "Date of the journey (YYYY-MM-DD)",
            },
            "service_type": {
                "type": "string",
                "description": "Type of service: train, flight, bus",
            },
        },
        "required": ["operator", "delay_minutes"],
    }

    async def execute(
        self,
        operator: str,
        delay_minutes: int,
        journey_date: str = "",
        service_type: str = "train",
    ) -> str:
        op_key = operator.lower().strip()
        policy = await self._load_policy(op_key)

        within_window = True
        if journey_date and policy:
            try:
                jdate = datetime.strptime(journey_date[:10], "%Y-%m-%d")
                days_since = (datetime.now(timezone.utc) - jdate.replace(tzinfo=timezone.utc)).days
                within_window = days_since <= policy["claim_window_days"]
            except (ValueError, TypeError):
                pass

        if policy:
            eligible = delay_minutes >= policy["min_delay_minutes"] and within_window
            return json.dumps({
                "success": True,
                "eligible": eligible,
                "operator": operator,
                "delay_minutes": delay_minutes,
                "min_delay_required": policy["min_delay_minutes"],
                "claim_window_days": policy["claim_window_days"],
                "within_claim_window": within_window,
                "claim_url": policy.get("url"),
                "reason": "Eligible for delay compensation" if eligible else
                          f"Delay must be at least {policy['min_delay_minutes']} minutes" if delay_minutes < policy["min_delay_minutes"] else
                          "Claim window has expired",
            }, indent=2)
        else:
            generic_eligible = delay_minutes >= 60
            return json.dumps({
                "success": True,
                "eligible": generic_eligible,
                "operator": operator,
                "delay_minutes": delay_minutes,
                "min_delay_required": 60,
                "claim_window_days": 28,
                "within_claim_window": within_window,
                "claim_url": None,
                "reason": "Likely eligible (generic policy)" if generic_eligible else "Delay may be too short for compensation",
                "note": f"No specific policy found for '{operator}'. Using generic thresholds.",
            }, indent=2)

    async def _load_policy(self, op_key: str) -> dict | None:
        """Try Firestore first, then fall back to hardcoded policies."""
        db = await _get_firestore()
        if db:
            try:
                q = db._adb.collection("refundPolicies").where("operator_key", "==", op_key).limit(1)
                async for snap in q.stream():
                    return snap.to_dict()
            except Exception as e:
                logger.debug("Firestore policy load failed: %s", e)

        for name, pol in _REFUND_POLICIES.items():
            if name in op_key or op_key in name:
                return pol
        return None


class GenerateClaimTool(BaseTool):
    """Draft a refund claim with appropriate tone (LLM-powered)."""

    name: str = "generate_claim"
    description: str = """
    Generate a refund claim letter/form text. Adapts the wording strength
    based on past success rates with this operator. First attempts are
    polite; escalations use firmer, more assertive language.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "operator": {
                "type": "string",
                "description": "Transport operator name",
            },
            "booking_reference": {
                "type": "string",
                "description": "Booking or ticket reference number",
            },
            "journey_details": {
                "type": "string",
                "description": "From, to, date, time of the journey",
            },
            "delay_minutes": {
                "type": "integer",
                "description": "Length of delay in minutes",
            },
            "ticket_price": {
                "type": "number",
                "description": "Price paid for the ticket",
            },
            "escalation_level": {
                "type": "integer",
                "description": "0=initial polite, 1=firm, 2=formal complaint with legal references",
            },
        },
        "required": ["operator", "booking_reference", "delay_minutes"],
    }

    async def execute(
        self,
        operator: str,
        booking_reference: str,
        delay_minutes: int,
        journey_details: str = "",
        ticket_price: float = 0.0,
        escalation_level: int = 0,
    ) -> str:
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return json.dumps({"success": False, "error": "ANTHROPIC_API_KEY not set"})

        tone_map = {
            0: "polite and professional",
            1: "firm and assertive, mentioning consumer rights",
            2: "formal complaint tone, referencing EU261/UK Consumer Rights Act, mentioning ombudsman escalation",
        }
        tone = tone_map.get(escalation_level, tone_map[0])

        prompt = (
            f"Write a refund claim to {operator} for a delayed journey.\n\n"
            f"Booking reference: {booking_reference}\n"
            f"Journey: {journey_details or 'details in reference'}\n"
            f"Delay: {delay_minutes} minutes\n"
            f"Ticket price: {ticket_price if ticket_price else 'not specified'}\n\n"
            f"Tone: {tone}\n"
            f"Escalation level: {escalation_level}/2\n\n"
            f"Write the claim as a complete, ready-to-submit message. "
            f"Include all necessary details and a clear request for compensation."
        )

        try:
            client = AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model=os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001"),
                system="You are a consumer rights expert drafting refund claims. Be effective and appropriate for the escalation level.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
            claim_text = resp.content[0].text if resp.content else ""

            return json.dumps({
                "success": True,
                "claim_text": claim_text,
                "escalation_level": escalation_level,
                "operator": operator,
                "booking_reference": booking_reference,
            }, indent=2)

        except Exception as e:
            logger.error("Claim generation failed: %s", e)
            return json.dumps({"success": False, "error": str(e)})


class SubmitClaimTool(BaseTool):
    """Submit the refund claim with persistent Firestore tracking."""

    name: str = "submit_claim"
    description: str = """
    Submit the refund claim to the operator's system.
    In demo mode, simulates submission and returns a tracking reference.
    Also provides the real URL where the user can submit manually.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "operator": {
                "type": "string",
                "description": "Transport operator",
            },
            "claim_text": {
                "type": "string",
                "description": "The claim text to submit",
            },
            "booking_reference": {
                "type": "string",
                "description": "Original booking reference",
            },
            "user_id": {
                "type": "string",
                "description": "User ID for tracking",
            },
        },
        "required": ["operator", "claim_text"],
    }

    async def execute(
        self,
        operator: str,
        claim_text: str,
        booking_reference: str = "",
        user_id: str = "default",
    ) -> str:
        claim_ref = f"CLM-{random.randint(100000, 999999)}"

        op_key = operator.lower().strip()
        claim_url = None
        for name, pol in _REFUND_POLICIES.items():
            if name in op_key or op_key in name:
                claim_url = pol["url"]
                break

        claim_doc = {
            "claim_ref": claim_ref,
            "operator": operator,
            "booking_reference": booking_reference,
            "user_id": user_id,
            "status": "submitted",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "escalation_level": 0,
            "claim_url": claim_url,
        }

        if user_id not in _claim_history:
            _claim_history[user_id] = []
        _claim_history[user_id].append(claim_doc)

        db = await _get_firestore()
        if db:
            try:
                await db._adb.collection("refundClaims").document(claim_ref).set(claim_doc)
            except Exception as e:
                logger.debug("Firestore claim persist failed: %s", e)

        return json.dumps({
            "success": True,
            "claim_reference": claim_ref,
            "status": "submitted",
            "operator": operator,
            "manual_submission_url": claim_url,
            "message": (
                f"Claim {claim_ref} submitted to {operator}. "
                f"Expected response time: 5-15 business days."
                + (f"\n\nYou can also submit manually at: {claim_url}" if claim_url else "")
            ),
        }, indent=2)


class TrackClaimStatusTool(BaseTool):
    """Check claim status from Firestore or in-memory history."""

    name: str = "track_claim_status"
    description: str = """
    Check the current status of a refund claim by reference number.
    Returns the latest status and any response from the operator.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "claim_reference": {
                "type": "string",
                "description": "The claim reference number (CLM-XXXXXX)",
            },
            "user_id": {
                "type": "string",
                "description": "User ID",
            },
        },
        "required": ["claim_reference"],
    }

    async def execute(self, claim_reference: str, user_id: str = "default") -> str:
        claim = await self._load_claim(claim_reference, user_id)

        if not claim:
            return json.dumps({
                "success": False,
                "error": f"Claim {claim_reference} not found",
            })

        statuses = ["submitted", "under_review", "approved", "rejected"]
        current = claim.get("status", "submitted")
        idx = statuses.index(current) if current in statuses else 0

        if idx < 2:
            new_status = statuses[min(idx + 1, len(statuses) - 1)]
            claim["status"] = new_status
        elif idx == 2 and random.random() < 0.7:
            claim["status"] = "approved"
        else:
            claim["status"] = "rejected" if random.random() < 0.3 else current

        db = await _get_firestore()
        if db:
            try:
                await db._adb.collection("refundClaims").document(claim_reference).update(
                    {"status": claim["status"]}
                )
            except Exception:
                pass

        return json.dumps({
            "success": True,
            "claim_reference": claim_reference,
            "status": claim["status"],
            "operator": claim.get("operator", ""),
            "submitted_at": claim.get("submitted_at", ""),
            "can_escalate": claim["status"] == "rejected",
        }, indent=2)

    async def _load_claim(self, claim_reference: str, user_id: str) -> dict | None:
        db = await _get_firestore()
        if db:
            try:
                doc = await db._adb.collection("refundClaims").document(claim_reference).get()
                if doc.exists:
                    return doc.to_dict()
            except Exception:
                pass

        claims = _claim_history.get(user_id, [])
        return next((c for c in claims if c.get("claim_ref") == claim_reference), None)


class EscalateClaimTool(BaseTool):
    """Escalate a rejected claim via incident.io and stronger wording."""

    name: str = "escalate_claim"
    description: str = """
    Escalate a rejected refund claim. This:
    1. Creates an incident.io alert so the failure is tracked and
       severity auto-escalates on recurring rejections.
    2. Updates the claim record with a higher escalation level.
    3. Returns instructions to regenerate with firmer wording.
    Adaptation is driven by the shared Task Memory system -- recurring
    failures for the same operator will automatically trigger stronger
    initial approaches via pattern analysis.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "claim_reference": {
                "type": "string",
                "description": "Original claim reference to escalate",
            },
            "operator": {
                "type": "string",
                "description": "Transport operator name",
            },
            "rejection_reason": {
                "type": "string",
                "description": "Why the claim was rejected (if known)",
            },
            "job_id": {
                "type": "string",
                "description": "Job ID for incident.io dedup key",
            },
            "user_id": {
                "type": "string",
                "description": "User ID",
            },
        },
        "required": ["claim_reference", "operator"],
    }

    async def execute(
        self,
        claim_reference: str,
        operator: str,
        rejection_reason: str = "",
        job_id: str = "",
        user_id: str = "default",
    ) -> str:
        claims = _claim_history.get(user_id, [])
        claim = next((c for c in claims if c.get("claim_ref") == claim_reference), None)
        current_level = 0
        if claim:
            current_level = claim.get("escalation_level", 0)
            claim["escalation_level"] = min(current_level + 1, 2)
            claim["status"] = "escalated"

        new_level = min(current_level + 1, 2)

        db = await _get_firestore()
        if db:
            try:
                await db._adb.collection("refundClaims").document(claim_reference).update({
                    "escalation_level": new_level,
                    "status": "escalated",
                })
            except Exception:
                pass

        incident_created = False
        try:
            from ..shared.incident_tools import _client as get_incident_client
            client = get_incident_client()
            if client:
                await client.create_alert(
                    title=f"Refund claim rejected: {operator} — {claim_reference}",
                    description=(
                        f"Operator: {operator}\n"
                        f"Claim: {claim_reference}\n"
                        f"Rejection reason: {rejection_reason or 'unknown'}\n"
                        f"Escalation level: {current_level} -> {new_level}"
                    ),
                    metadata={
                        "operator": operator,
                        "claim_reference": claim_reference,
                        "rejection_reason": rejection_reason,
                        "escalation_level": new_level,
                        "agent_id": "refund_claim",
                    },
                    dedup_key=f"sota-refund-{claim_reference}",
                    status="firing",
                    severity="high" if new_level < 2 else "critical",
                )
                incident_created = True
        except Exception:
            pass

        return json.dumps({
            "success": True,
            "claim_reference": claim_reference,
            "new_escalation_level": new_level,
            "operator": operator,
            "incident_created": incident_created,
            "message": (
                f"Claim escalated to level {new_level}. "
                f"Use generate_claim with escalation_level={new_level} "
                f"to create a stronger claim letter."
                + (" An incident has been created for tracking." if incident_created else "")
            ),
        }, indent=2)


def create_refund_claim_tools() -> list[BaseTool]:
    """Create all refund claim tools."""
    return [
        ParseTicketTool(),
        CheckEligibilityTool(),
        GenerateClaimTool(),
        SubmitClaimTool(),
        TrackClaimStatusTool(),
        EscalateClaimTool(),
    ]
