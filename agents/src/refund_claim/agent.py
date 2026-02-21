"""
Refund Claim Agent -- SOTA on Base

Automates refund claims for delayed transport:
1. Parses ticket emails to extract journey details
2. Checks eligibility against operator policies
3. Generates and submits refund claims
4. Tracks claim status and escalates rejections
5. Learns which operators need stronger initial wording
"""

import os
import asyncio
import logging
from typing import Optional

from ..shared.agent_runner import AgentRunner, LLMClient
from ..shared.tool_base import ToolManager

from ..shared.base_agent import BaseArchiveAgent, AgentCapability, ActiveJob
from ..shared.auto_bidder import AutoBidderMixin
from ..shared.config import JobType, JOB_TYPE_LABELS
from ..shared.events import JobPostedEvent
from ..shared.wallet_tools import create_wallet_tools
from ..shared.bidding_tools import create_bidding_tools
from ..shared.butler_comms import create_butler_comm_tools

from .tools import create_refund_claim_tools

try:
    from ..shared.incident_tools import create_incident_tools
except Exception:
    create_incident_tools = None  # type: ignore

logger = logging.getLogger(__name__)


REFUND_SYSTEM_PROMPT = """
You are the Refund Claim Agent for SOTA, specializing in automating
refund claims for delayed trains, flights, and other transport.

## YOUR WORKFLOW
1. If ticket text is provided, call `parse_ticket` to extract details.
2. Call `check_eligibility` with the operator and delay minutes.
3. If eligible, call `generate_claim` to draft the claim letter.
4. Ask for user confirmation before submitting.
5. Call `submit_claim` to submit and get a tracking reference.
6. Optionally call `track_claim_status` to check progress.

## ADAPTIVE BEHAVIOR (via Task Memory + incident.io)
- The system learns from past outcomes via the shared Task Memory.
  If similar refund claims have failed before, the HISTORICAL CONTEXT
  section at the top of your prompt will tell you the failure patterns.
- Adapt based on that context: if past claims for the same operator
  were rejected, start with a higher escalation level.
- If a claim is rejected, call `escalate_claim` to create an incident.io
  alert for tracking, then call `generate_claim` with the higher level.
- You can also call `create_incident` directly for severe issues.

## ESCALATION LEVELS
- Level 0: Polite, professional request
- Level 1: Firm, cites consumer rights
- Level 2: Formal complaint, references legislation, mentions ombudsman

## BUTLER COMMUNICATION (Marketplace Jobs)
When executing a marketplace job:
1. Call `notify_butler` with status='in_progress' when starting.
2. If you need ticket details, call `request_butler_data`
   with data_type='clarification'.
3. Before submitting, call `request_butler_data` with
   data_type='confirmation' to get user approval.
4. Call `notify_butler` with status='completed' and claim details.

## FORMATTING RULES
- NEVER use markdown syntax.
- Write plain text only.
- Keep the user informed at each step.
"""


class RefundClaimAgent(AutoBidderMixin, BaseArchiveAgent):
    """
    Refund Claim Agent for SOTA.
    Automates refund claims with adaptive escalation.
    """

    agent_type = "refund_claim"
    agent_name = "SOTA Refund Claim Agent"
    capabilities = [AgentCapability.DATA_ANALYSIS]
    supported_job_types = [JobType.REFUND_CLAIM]

    min_profit_margin = 0.10
    max_concurrent_jobs = 8
    auto_bid_enabled = True
    bid_price_ratio = 0.70
    bid_eta_seconds = 180

    async def _create_llm_agent(self) -> AgentRunner:
        all_tools: list = []
        all_tools.extend(create_refund_claim_tools())
        all_tools.extend(create_butler_comm_tools())
        if create_incident_tools:
            all_tools.extend(create_incident_tools())
        all_tools.extend(create_wallet_tools(self.wallet))
        all_tools.extend(create_bidding_tools(self._contracts, self.agent_type))

        model_name = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20241022")

        return AgentRunner(
            name="refund_claim",
            description="Automated refund claim agent for SOTA on Base",
            system_prompt=REFUND_SYSTEM_PROMPT,
            max_steps=15,
            tools=ToolManager(all_tools),
            llm=LLMClient(model=model_name),
        )

    def get_bidding_prompt(self, job: JobPostedEvent) -> str:
        job_type_label = JOB_TYPE_LABELS.get(JobType(job.job_type), "Unknown")
        budget_usdc = job.budget / 10**6
        return (
            f"Auto-bid mode: will place bid on job {job.job_id} "
            f"({job_type_label}) budget {budget_usdc} USDC."
        )

    async def execute_job(self, job: ActiveJob) -> dict:
        """Execute a refund claim job."""
        service_type = ""
        booking_reference = ""
        delay_details = ""
        ticket_email = ""
        operator = ""

        if "=" in job.description:
            try:
                parts = job.description.split(": ", 1)[-1]
                for param in parts.split(", "):
                    if "=" in param:
                        k, v = param.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k == "service_type":
                            service_type = v
                        elif k == "booking_reference":
                            booking_reference = v
                        elif k == "delay_details":
                            delay_details = v
                        elif k == "ticket_email":
                            ticket_email = v
                        elif k == "operator":
                            operator = v
            except Exception:
                pass

        prompt = (
            f"You are executing marketplace job #{job.job_id}.\n\n"
            f"Job description: {job.description}\n\n"
            f"## EXTRACTED PARAMETERS:\n"
            f"- Service type: {service_type or 'determine from ticket'}\n"
            f"- Booking reference: {booking_reference or 'extract from ticket'}\n"
            f"- Delay details: {delay_details or 'determine from ticket'}\n"
            f"- Ticket email: {ticket_email or 'not provided'}\n"
            f"- Operator: {operator or 'determine from ticket'}\n\n"
            f"## YOUR TASK:\n"
            f"1. Call `notify_butler` with job_id='{job.job_id}', "
            f"status='in_progress', message='Processing your refund claim...'\n"
            f"2. If ticket text is available, call `parse_ticket`\n"
            f"3. If missing critical info, call `request_butler_data` "
            f"with data_type='clarification'\n"
            f"4. Call `check_eligibility` with operator and delay\n"
            f"5. If eligible, call `generate_claim`\n"
            f"6. Call `request_butler_data` with data_type='confirmation' "
            f"showing the draft claim\n"
            f"7. If confirmed, call `submit_claim`\n"
            f"8. Call `notify_butler` with status='completed' and claim details\n"
        )

        # Enrich prompt with historical pattern analysis
        pattern_analysis = getattr(job, "params", {}).get("pattern_analysis")
        if pattern_analysis:
            from ..shared.task_memory import build_adaptation_prompt
            adaptation = build_adaptation_prompt(pattern_analysis)
            if adaptation:
                prompt = adaptation + prompt

        try:
            if self.llm_agent:
                result = await self.llm_agent.run(prompt)
                return {"success": True, "result": result, "job_id": job.job_id}
            return {"success": False, "error": "LLM agent not initialized", "job_id": job.job_id}
        except Exception as e:
            logger.error("Refund claim job #%s failed: %s", job.job_id, e)
            return {"success": False, "error": str(e), "job_id": job.job_id}


async def create_refund_claim_agent() -> RefundClaimAgent:
    """Factory function to create and initialize a Refund Claim Agent."""
    agent = RefundClaimAgent()
    await agent.initialize()
    agent.register_on_board()
    return agent


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    print("SOTA Refund Claim Agent")
    print("=" * 60)
    agent = await create_refund_claim_agent()
    print(f"\nStatus: {agent.get_status()}")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        print("\nRefund Claim Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
