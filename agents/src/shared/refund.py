"""
Refund Trigger — calls the Next.js refund endpoint to issue a Stripe
card refund and on-chain escrow refund for a failed job.
"""

import os
import logging
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

NEXTJS_BASE_URL = os.getenv("NEXTJS_BASE_URL", "http://localhost:3000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


async def trigger_refund(
    job_id: str,
    reason: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Request a Stripe + on-chain refund for a failed job.

    Calls POST /api/stripe/refund on the Next.js frontend, which:
      1. Looks up the Payment record by jobId
      2. Calls Escrow.refund(jobId) on-chain (if funded)
      3. Calls stripe.refunds.create(paymentIntentId)
      4. Updates the Payment record

    Returns the JSON response from the refund endpoint.
    Returns an error dict (without raising) if the request fails.
    """
    if not INTERNAL_API_KEY:
        logger.warning("INTERNAL_API_KEY not set — skipping refund for job %s", job_id)
        return {"success": False, "error": "INTERNAL_API_KEY not configured"}

    url = f"{NEXTJS_BASE_URL}/api/stripe/refund"
    payload = {"job_id": job_id}
    if reason:
        payload["reason"] = reason

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"x-internal-api-key": INTERNAL_API_KEY},
            )

        data = resp.json()

        if resp.status_code == 404:
            # No payment record — job was likely crypto-only, not a Stripe payment
            logger.info("No Stripe payment found for job %s (crypto-only?)", job_id)
            return data

        if resp.status_code == 200:
            logger.info(
                "Refund succeeded for job %s: stripe=%s, escrow_tx=%s",
                job_id,
                data.get("stripeRefundId"),
                data.get("escrowRefundTxHash"),
            )
            return data

        logger.error(
            "Refund request failed for job %s (HTTP %d): %s",
            job_id, resp.status_code, data,
        )
        return data

    except httpx.TimeoutException:
        logger.error("Refund request timed out for job %s", job_id)
        return {"success": False, "error": "timeout"}
    except Exception as e:
        logger.error("Refund request error for job %s: %s", job_id, e)
        return {"success": False, "error": str(e)}
