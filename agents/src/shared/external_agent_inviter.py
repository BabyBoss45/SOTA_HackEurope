"""
External ClawBot Agent Inviter

Discovers active ExternalAgents from the database, matches them to a job
by capabilities and supported domains, fans out HTTP bid_request calls
concurrently, and appends valid bids to the JobBoard's in-memory bid list.

This runs as a parallel asyncio task alongside internal worker evaluations
within the JobBoard's 60-second bid window.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional

import asyncpg
import httpx

from agents.src.shared.hmac_signer import HMACSigner
from agents.src.shared.job_board import Bid, JobListing

logger = logging.getLogger(__name__)

# Rate limiting: max bids per minute per external agent (process-local)
_bid_rate_tracker: Dict[str, Deque[float]] = defaultdict(deque)
MAX_BIDS_PER_MINUTE = 10
RATE_WINDOW_SECONDS = 60


def _check_rate_limit(agent_id: str) -> bool:
    """Return True if the agent is allowed to bid, False if rate-limited."""
    now = time.time()
    times = _bid_rate_tracker[agent_id]
    # Prune old entries outside the window
    while times and now - times[0] > RATE_WINDOW_SECONDS:
        times.popleft()
    if len(times) >= MAX_BIDS_PER_MINUTE:
        return False
    times.append(now)
    return True


class ExternalAgentInviter:
    """
    Sends HTTP bid_request invitations to active external ClawBot agents.

    External agents are expected to run a FastAPI server created via
    sota_sdk.server.create_app() with custom /bid_request and /execute
    endpoints added through SOTAAgent.register_routes().
    """

    def __init__(self, pool: asyncpg.Pool, signer: HMACSigner) -> None:
        self._pool = pool
        self._signer = signer

    async def invite_for_job(
        self,
        job: JobListing,
        bid_list: List[Bid],
        timeout_seconds: int = 50,
    ) -> None:
        """
        Discover matching external agents, fan out bid_request POSTs, and
        append valid bids to bid_list before timeout_seconds elapses.

        This is safe to call concurrently with internal worker _solicit_bid
        tasks; asyncio's GIL ensures list.append() is atomic.
        """
        try:
            agents = await self._fetch_matching_agents(job)
        except Exception as exc:
            logger.warning("ExternalAgentInviter: DB fetch failed: %s", exc)
            return

        if not agents:
            return

        logger.info(
            "ExternalAgentInviter: inviting %d external agent(s) for job %s",
            len(agents), job.job_id,
        )

        tasks = [
            asyncio.create_task(
                self._solicit_external_bid(agent, job, bid_list)
            )
            for agent in agents
        ]

        # Wait up to timeout_seconds; cancel any that are still running
        done, pending = await asyncio.wait(tasks, timeout=timeout_seconds)
        for t in pending:
            t.cancel()

    async def _fetch_matching_agents(self, job: JobListing) -> List[Dict[str, Any]]:
        """
        Query the DB for active ExternalAgents whose capabilities overlap
        with the job tags and whose supported domains overlap with job domains
        (or the job has no domain restriction).
        """
        job_tags = list({t.lower() for t in job.tags})
        job_domains = list({
            d.lower()
            for d in job.metadata.get('domains', [])
            if isinstance(d, str)
        })

        if job_domains:
            rows = await self._pool.fetch(
                """
                SELECT "agentId", name, endpoint, capabilities,
                       "supportedDomains", "walletAddress", "publicKey"
                FROM "ExternalAgent"
                WHERE status = 'active'
                  AND (SELECT array_agg(LOWER(c)) FROM unnest(capabilities) c) && $1::text[]
                  AND (SELECT array_agg(LOWER(d)) FROM unnest("supportedDomains") d) && $2::text[]
                """,
                job_tags,
                job_domains,
            )
        else:
            # No domain restriction — match on capabilities only
            rows = await self._pool.fetch(
                """
                SELECT "agentId", name, endpoint, capabilities,
                       "supportedDomains", "walletAddress", "publicKey"
                FROM "ExternalAgent"
                WHERE status = 'active'
                  AND (SELECT array_agg(LOWER(c)) FROM unnest(capabilities) c) && $1::text[]
                """,
                job_tags,
            )

        return [dict(r) for r in rows]

    async def _solicit_external_bid(
        self,
        agent: Dict[str, Any],
        job: JobListing,
        bid_list: List[Bid],
    ) -> None:
        """
        POST bid_request to a single external agent and append a valid Bid.

        The agent's /bid_request endpoint is expected to use
        DefaultBidStrategy.evaluate() from sota_sdk.
        """
        agent_id: str = agent['agentId']

        if not _check_rate_limit(agent_id):
            logger.debug("Rate-limiting external agent %s", agent_id)
            return

        payload = {
            'jobId': job.job_id,
            'description': job.description,
            'tags': job.tags,
            'budgetUsdc': job.budget_usdc,
            'metadata': job.metadata,
        }

        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        raw_key: Optional[str] = agent.get('publicKey')
        if raw_key:
            try:
                # Decrypt the stored AES-256 key before signing
                decrypted_key = _decrypt_stored_key(raw_key)
                headers['X-SOTA-Signature'] = self._signer.sign(payload, decrypted_key)
            except Exception as exc:
                logger.warning(
                    "Could not sign payload for agent %s: %s", agent_id, exc
                )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{agent['endpoint']}/bid_request",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code == 400 or resp.status_code == 204:
                    # Agent declined (DefaultBidStrategy returned None)
                    return
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.debug("External agent %s bid_request failed: %s", agent_id, exc)
            return

        # Validate response schema
        try:
            bid_price = float(data['bidPrice'])
            confidence = float(data['confidence'])
            estimated_time = int(data['estimatedTimeSec'])
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Agent %s returned invalid bid schema: %s", agent_id, exc)
            return

        if bid_price <= 0 or bid_price > job.budget_usdc:
            logger.debug(
                "Agent %s bid %.4f USDC rejected (budget=%.4f)",
                agent_id, bid_price, job.budget_usdc,
            )
            return
        if not (0.0 <= confidence <= 1.0):
            logger.debug("Agent %s bid has invalid confidence %.4f", agent_id, confidence)
            return

        bid = Bid(
            bid_id=str(uuid.uuid4())[:8],
            job_id=job.job_id,
            bidder_id=f"external:{agent_id}",
            bidder_address=agent['walletAddress'],
            amount_usdc=bid_price,
            estimated_seconds=estimated_time,
            tags=job.tags,
            metadata={
                'source': 'external',
                'externalAgentId': agent_id,
                'externalAgentName': agent['name'],
                'confidence': confidence,
                'riskFactors': data.get('riskFactors', []),
            },
        )
        bid_list.append(bid)

        logger.info(
            "External bid received: agent=%s  price=%.4f USDC  eta=%ds  confidence=%.2f",
            agent_id, bid_price, estimated_time, confidence,
        )

        # Persist as AgentJobUpdate (fire-and-forget, best-effort)
        asyncio.create_task(
            _persist_bid_update(self._pool, job.job_id, agent, bid_price, confidence, estimated_time)
        )


def _decrypt_stored_key(encrypted: str) -> str:
    """
    Decrypt an AES-256-CBC key stored in ExternalAgent.publicKey.
    Mirrors src/lib/auth.ts decryptApiKey().
    """
    import os
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    enc_key = os.getenv('ENCRYPTION_KEY', '0123456789abcdef0123456789abcdef')
    iv_hex, cipher_hex = encrypted.split(':', 1)
    iv = bytes.fromhex(iv_hex)
    ciphertext = bytes.fromhex(cipher_hex)
    key = enc_key.encode('utf-8')[:32]

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    dec = cipher.decryptor()
    padded = dec.update(ciphertext) + dec.finalize()

    # PKCS7 unpad
    pad_len = padded[-1]
    return padded[:-pad_len].decode('utf-8')


async def _persist_bid_update(
    pool: asyncpg.Pool,
    job_id: str,
    agent: Dict[str, Any],
    bid_price: float,
    confidence: float,
    estimated_time: int,
) -> None:
    """Fire-and-forget: save bid to AgentJobUpdate using the shared pool."""
    try:
        import json as _json

        await pool.execute(
            """
            INSERT INTO "AgentJobUpdate" ("jobId", agent, status, message, data, "createdAt")
            VALUES ($1, $2, 'bid_submitted', $3, $4::jsonb, NOW())
            """,
            job_id,
            f"external:{agent['name']}",
            f"Bid: {bid_price:.4f} USDC",
            _json.dumps({
                'externalAgentId': agent['agentId'],
                'bidPrice': bid_price,
                'confidence': confidence,
                'estimatedTimeSec': estimated_time,
                'source': 'external',
            }),
        )
    except Exception as exc:
        logger.debug("_persist_bid_update failed: %s", exc)
