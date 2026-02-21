"""
Caller Agent — SOTA on Base

Uses ElevenLabs Conversational AI over Twilio to make real phone calls
that can listen, adapt, and actually complete bookings.
"""

import os
import re
import asyncio
import logging
from typing import Optional

from pydantic import Field

from ..shared.agent_runner import AgentRunner, LLMClient
from ..shared.tool_base import ToolManager

from ..shared.base_agent import BaseArchiveAgent, AgentCapability, ActiveJob, BidDecision
from ..shared.auto_bidder import AutoBidderMixin
from ..shared.config import JobType, JOB_TYPE_LABELS
from ..shared.events import JobPostedEvent
from ..shared.wallet_tools import create_wallet_tools
from ..shared.bidding_tools import create_bidding_tools

from .tools import create_caller_tools

logger = logging.getLogger(__name__)

_CONFIRMED_PATTERNS = [
    r"\bconfirm", r"\bbooked\b", r"\breserved\b", r"\bsee you\b",
    r"\ball set\b", r"\btable.{0,20}ready", r"\broom.{0,20}ready",
    r"\bgot you down\b", r"\byou'?re all\b", r"\bwe'?ll have",
    r"\bwe have.{0,15}(?:table|room|spot|space)",
]
_DENIED_PATTERNS = [
    r"fully booked", r"no availability", r"sold out",
    r"no tables?\b", r"no rooms?\b", r"cannot accommodate",
    r"unfortunately.{0,30}(?:full|available|book)",
    r"don'?t have.{0,20}(?:space|availability|opening)",
]
_VOICEMAIL_PATTERNS = [
    r"voicemail", r"leave a message", r"after the (?:tone|beep)",
    r"please record", r"not available.{0,20}message",
]


def _extract_venue_text(transcript_text: str) -> str:
    """Pull out only the venue (USER) side of the conversation so we
    don't false-positive on words the *agent* said."""
    lines = transcript_text.split("\n")
    venue_lines = []
    for line in lines:
        stripped = line.strip().lower()
        if stripped.startswith("user:"):
            venue_lines.append(stripped[5:].strip())
    return " ".join(venue_lines)


def _detect_booking_outcome(transcript_text: str, analysis: dict) -> str:
    """Determine booking outcome from the conversation transcript and
    ElevenLabs post-call analysis."""
    call_ok = str((analysis or {}).get("call_successful", "")).lower().strip()
    if call_ok in ("true", "success", "yes"):
        return "confirmed"
    if call_ok in ("false", "failure", "no"):
        return "denied"

    if not transcript_text.strip():
        return "no_conversation"

    # Also check the summary for voicemail indicators
    summary = str((analysis or {}).get("transcript_summary", "")).lower()
    full_text = (transcript_text + " " + summary).lower()
    for pat in _VOICEMAIL_PATTERNS:
        if re.search(pat, full_text):
            return "voicemail"

    # Only look at what the VENUE said (USER role) to avoid matching
    # words the agent itself spoke (e.g. "please confirm").
    venue_text = _extract_venue_text(transcript_text)

    for pat in _DENIED_PATTERNS:
        if re.search(pat, venue_text):
            return "denied"
    for pat in _CONFIRMED_PATTERNS:
        if re.search(pat, venue_text):
            return "confirmed"

    return "unknown"


def _build_chat_summary(
    outcome: str,
    phone_number: str,
    booking_type: str,
    guests,
    date: str,
    time_slot: str,
    user_name: str,
    summary: str,
    transcript_text: str,
) -> str:
    """Build a human-readable chat summary from the call outcome."""
    base = (
        f"I called {phone_number} to make a {booking_type} reservation "
        f"for {guests} guests on {date} at {time_slot} under {user_name}."
    )
    if outcome == "confirmed":
        result = "The booking was confirmed!"
    elif outcome == "denied":
        result = "Unfortunately, they couldn't accommodate the booking."
    elif outcome == "voicemail":
        result = (
            "The call went to voicemail. I left a message with the "
            "booking details and asked them to call back to confirm."
        )
    elif outcome == "no_conversation":
        result = "The call connected but no conversation took place."
    else:
        result = (
            "The call completed but I couldn't determine the booking "
            "outcome from the conversation."
        )

    parts = [base, result]
    if summary:
        parts.append(f"Call summary: {summary}")
    return " ".join(parts)


CALLER_SYSTEM_PROMPT = """
You are the Caller Agent for SOTA, specializing in phone-based bookings
and verifications via ElevenLabs Conversational AI over Twilio.

## CRITICAL SAFETY RULE
You NEVER provide credit card numbers, bank details, or any payment
information during calls. If a venue asks for a card to hold a booking,
say: "The guest will provide payment details directly. Could we hold
the reservation under their name for now?" If a card is absolutely
required, ask for a direct number so the guest can call themselves.

## YOUR CAPABILITIES
1. Conversational Calls: Use make_elevenlabs_call for real, adaptive
   phone conversations (books restaurants, hotels, verifies info).
2. Conversation Status: Use get_elevenlabs_conversation to check
   call transcripts and outcomes.
3. SMS: Use send_sms for follow-up confirmations.
4. Delivery: After calls, upload results and submit delivery proofs.

## WORKFLOW
- Primary: make_elevenlabs_call → poll get_elevenlabs_conversation
- After call completes: upload_call_result → submit_delivery
"""


class CallerAgent(AutoBidderMixin, BaseArchiveAgent):
    """
    Caller Agent for SOTA.
    
    Extends BaseArchiveAgent with phone verification-specific logic.
    Mixes in AutoBidderMixin to participate in the JobBoard marketplace.
    """
    
    agent_type = "caller"
    agent_name = "SOTA Caller Agent"
    capabilities = [
        AgentCapability.PHONE_CALL,
    ]
    # Only handle booking and call verification jobs
    supported_job_types = [
        JobType.HOTEL_BOOKING,
        JobType.RESTAURANT_BOOKING,
        JobType.CALL_VERIFICATION,
    ]
    
    # Bidding configuration
    min_profit_margin = 0.20  # 20% margin (calls are more expensive)
    max_concurrent_jobs = 2   # Fewer concurrent calls
    auto_bid_enabled = True
    bid_price_ratio = 0.90     # caller bids 90% of budget (more expensive service)
    
    async def _create_llm_agent(self) -> AgentRunner:
        """Create agent runner for tooling (bidding is auto)."""
        all_tools = []
        all_tools.extend(create_caller_tools())
        all_tools.extend(create_wallet_tools(self.wallet))
        all_tools.extend(create_bidding_tools(self._contracts, self.agent_type))

        model_name = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022")

        return AgentRunner(
            name="caller",
            description="Caller Agent for phone verification tasks",
            system_prompt=CALLER_SYSTEM_PROMPT,
            max_steps=15,
            tools=ToolManager(all_tools),
            llm=LLMClient(model=model_name),
        )

    def get_bidding_prompt(self, job: JobPostedEvent) -> str:
        """Not used for auto-bid; kept for compatibility."""
        job_type_label = JOB_TYPE_LABELS.get(JobType(job.job_type), "Unknown")
        budget_usdc = job.budget / 10**6
        return f"Auto-bid mode: will place 1 USDC bid on job {job.job_id} ({job_type_label}) budget {budget_usdc} USDC."

    async def _evaluate_and_bid(self, job: JobPostedEvent):
        """
        Auto-bid 1 USDC on any job type.
        """
        if len(self.active_jobs) >= self.max_concurrent_jobs:
            logger.warning("At capacity, skipping job %s", job.job_id)
            return

        decision = BidDecision(
            should_bid=True,
            proposed_amount=1_000_000,  # 1 USDC
            estimated_time=1800,  # 30 min
            reasoning="Auto-bid caller on all job types",
            confidence=0.9,
        )

        if decision.should_bid and self._contracts:
            try:
                from agents.src.shared.contracts import place_bid

                bid_id = place_bid(
                    self._contracts,
                    job.job_id,
                    decision.proposed_amount,
                    decision.estimated_time,
                    f"ipfs://{self.agent_type}-bid-{job.job_id}",
                )
                logger.info("Auto-bid placed job_id=%s bid_id=%s", job.job_id, bid_id)
            except Exception as e:
                logger.error("Failed to place auto-bid on job %s: %s", job.job_id, e)
        elif decision.should_bid and not self._contracts:
            logger.error("Contracts not initialized; cannot bid on job #%s", job.job_id)

    async def execute_job(self, job: ActiveJob) -> dict:
        """Execute a booking/verification call via ElevenLabs ConvAI.

        The AI agent has a real conversation with the venue, listens to
        their responses, and adapts in real-time.  After the call we poll
        the ElevenLabs API for the transcript and detect whether the
        booking was confirmed or denied.
        """
        import json as _json
        import httpx as _httpx

        params = job.params or {}
        phone_number = params.get("phone_number", "") or "+447553293952"

        tool_tag = (job.metadata_uri or "").lower() if hasattr(job, "metadata_uri") else ""
        desc_lower = (job.description or "").lower()
        if "hotel" in tool_tag or "hotel" in desc_lower:
            booking_type = "hotel"
        elif "restaurant" in tool_tag or "restaurant" in desc_lower:
            booking_type = "restaurant"
        else:
            booking_type = "restaurant"

        location = params.get("location") or params.get("city") or ""
        date = params.get("date") or params.get("check_in") or "tomorrow"
        check_out = params.get("check_out") or ""
        time_slot = params.get("time") or ("3pm" if booking_type == "hotel" else "8pm")
        guests = params.get("guests") or params.get("num_of_people") or 2
        cuisine = params.get("cuisine") or ""
        user_name = params.get("user_name") or "SOTA Guest"
        special_requests = params.get("special_requests") or ""
        if booking_type == "hotel" and check_out:
            special_requests = f"Check-out: {check_out}. {special_requests}".strip()

        # -- No phone number: ask the user for it --
        if not phone_number:
            logger.info("No phone_number — asking user for job #%s", job.job_id)
            return {
                "success": True,
                "chat_summary": (
                    f"I'd be happy to help with your {booking_type} booking "
                    f"in {location or 'your area'} for {guests} guests on "
                    f"{date} at {time_slot}. "
                    f"To make the call, I'll need the venue's phone number."
                ),
                "job_id": job.job_id,
            }

        logger.info(
            "Executing call job #%s → %s (%s)",
            job.job_id, phone_number, job.description,
        )

        # -- Verify ElevenLabs config --
        el_api_key = os.getenv("ELEVENLABS_API_KEY")
        el_phone_id = os.getenv("ELEVENLABS_PHONE_ID")
        el_agent_id = (
            os.getenv("ELEVENLABS_CALLER_AGENT_ID")
            or os.getenv("ELEVENLABS_AGENT_ID")
        )

        if not all([el_api_key, el_phone_id, el_agent_id]):
            missing = []
            if not el_api_key:
                missing.append("ELEVENLABS_API_KEY")
            if not el_phone_id:
                missing.append("ELEVENLABS_PHONE_ID")
            if not el_agent_id:
                missing.append("ELEVENLABS_CALLER_AGENT_ID")
            return {
                "success": False,
                "error": f"ElevenLabs not configured: missing {', '.join(missing)}",
                "chat_summary": (
                    "I couldn't place the call because the voice AI "
                    "service isn't fully configured."
                ),
            }

        # -- 1. Initiate ElevenLabs ConvAI call --
        logger.info("Using ElevenLabs ConvAI via Twilio")
        from .tools import MakeElevenLabsCallTool
        tool = MakeElevenLabsCallTool()
        raw = await tool.execute(
            to_number=phone_number,
            user_name=user_name,
            time=time_slot,
            date=str(date),
            num_of_people=int(guests),
            booking_type=booking_type,
            cuisine=cuisine,
            location=location,
            special_requests=special_requests,
        )
        result = _json.loads(raw)

        if not result.get("success"):
            error = result.get("error", "Failed to initiate call")
            logger.error("ElevenLabs call initiation failed: %s", error)
            return {
                "success": False,
                "error": error,
                "chat_summary": (
                    f"I tried to call {phone_number} but couldn't "
                    f"connect: {error}"
                ),
            }

        body = result.get("body", {})
        conversation_id = (
            body.get("conversation_id")
            or body.get("call_id")
            or body.get("id")
        )
        logger.info(
            "Call initiated → conversation_id=%s", conversation_id,
        )

        if not conversation_id:
            return {
                "success": True,
                "method": "elevenlabs_convai",
                "phone_number": phone_number,
                "call_data": body,
                "chat_summary": (
                    f"Call placed to {phone_number}. "
                    f"The AI concierge is handling the conversation now."
                ),
            }

        # -- 2. Poll ElevenLabs for conversation completion --
        conv_data: dict = {}
        final_status = "unknown"
        max_polls = 30          # 30 * 5s = 150s max
        not_found_grace = 6     # allow up to 30s for conversation to appear

        for attempt in range(max_polls):
            await asyncio.sleep(5)
            try:
                async with _httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}",
                        headers={"xi-api-key": el_api_key},
                    )
                    if resp.status_code == 404:
                        if attempt < not_found_grace:
                            continue
                        logger.warning(
                            "Conversation %s still 404 after %ds",
                            conversation_id, (attempt + 1) * 5,
                        )
                        continue
                    resp.raise_for_status()
                    conv_data = resp.json()
                    final_status = conv_data.get("status", "unknown")
                    logger.info(
                        "Poll %d: status=%s", attempt + 1, final_status,
                    )
                    if final_status in (
                        "done", "completed", "ended", "failed", "error"
                    ):
                        break
            except Exception as exc:
                logger.warning("Poll %d error: %s", attempt + 1, exc)

        # -- 3. Extract transcript, analysis, outcome --
        transcript_turns: list[dict] = []
        transcript_text = ""
        raw_transcript = conv_data.get("transcript") or []
        if isinstance(raw_transcript, list):
            for turn in raw_transcript:
                role = turn.get("role", "unknown")
                msg = turn.get("message") or ""
                if not msg or msg == "None":
                    continue
                transcript_turns.append({"role": role, "message": msg})
                transcript_text += f"{role}: {msg}\n"
        elif isinstance(raw_transcript, str):
            transcript_text = raw_transcript

        analysis = conv_data.get("analysis") or {}
        summary = (
            analysis.get("transcript_summary")
            or analysis.get("summary")
            or conv_data.get("summary")
            or ""
        )
        metadata = conv_data.get("metadata") or {}
        duration = metadata.get("call_duration_secs")

        outcome = _detect_booking_outcome(transcript_text, analysis)

        logger.info(
            "Call %s finished: status=%s outcome=%s duration=%s",
            conversation_id, final_status, outcome, duration,
        )

        # -- 4. Build response --
        chat_summary = _build_chat_summary(
            outcome=outcome,
            phone_number=phone_number,
            booking_type=booking_type,
            guests=guests,
            date=date,
            time_slot=time_slot,
            user_name=user_name,
            summary=summary,
            transcript_text=transcript_text,
        )

        return {
            "success": outcome == "confirmed" or final_status == "done",
            "method": "elevenlabs_convai",
            "conversation_id": conversation_id,
            "phone_number": phone_number,
            "status": final_status,
            "outcome": outcome,
            "duration_seconds": duration,
            "transcript": transcript_turns,
            "summary": summary,
            "booking_details": {
                "type": booking_type,
                "guests": guests,
                "date": date,
                "time": time_slot,
                "name": user_name,
                "location": location,
                "cuisine": cuisine,
            },
            "chat_summary": chat_summary,
        }


async def create_caller_agent(db=None) -> CallerAgent:
    """Factory function to create and initialize a Caller Agent"""
    agent = CallerAgent()
    await agent.initialize()
    await agent.register_on_board(db=db)          # register on JobBoard marketplace
    return agent


async def main():
    """Run the Caller Agent"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("📞 Archive Caller Agent")
    print("=" * 60)
    
    agent = await create_caller_agent()
    print(f"\n📊 Status: {agent.get_status()}")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        print("\n👋 Caller Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())

