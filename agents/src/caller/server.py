"""
Caller Agent Server

FastAPI server that:
1. Exposes A2A endpoints for agent communication
2. Runs the event listener for blockchain events
3. Provides health/status endpoints
"""

import os
import asyncio
import logging
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import uvicorn
import httpx

from ..shared.a2a import (
    A2AMessage, 
    A2AResponse, 
    A2AMethod,
    A2AErrorCode,
    verify_message,
    is_message_fresh,
    create_error_response,
    create_success_response,
)

from .agent import CallerAgent, create_caller_agent
from ..shared.contracts import submit_delivery
from ..shared.base_agent import ActiveJob

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global agent instance
agent: CallerAgent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global agent

    logger.info("Starting SOTA Caller Agent...")

    # Initialize and start agent
    agent = await create_caller_agent()
    await agent.start()

    # Connect to marketplace Hub (if SOTA_HUB_URL is set)
    from ..shared.hub_connector import HubConnector
    connector = HubConnector(agent)
    hub_task = asyncio.create_task(connector.run())

    yield

    # Cleanup
    connector.stop()
    hub_task.cancel()
    if agent:
        agent.stop()
    logger.info("Caller Agent stopped")


app = FastAPI(
    title="SOTA Caller Agent",
    description="Phone verification agent for SOTA on Solana",
    version="0.1.0",
    lifespan=lifespan
)


# Health & Status Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "agent": "caller"}


@app.get("/status")
async def get_status():
    """Get agent status"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent.get_status()


@app.get("/wallet")
async def get_wallet_info():
    """Get wallet information"""
    if not agent or not agent.wallet:
        raise HTTPException(status_code=503, detail="Wallet not configured")
    
    balance = agent.wallet.get_balance()
    return {
        "address": agent.wallet.address,
        "native_balance": str(balance.native),
        "usdc_balance": str(balance.usdc),
    }


@app.get("/jobs")
async def get_active_jobs():
    """Get active jobs"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    return {
        "active_jobs": [
            {
                "job_id": job.job_id,
                "status": job.status,
                "job_type": job.job_type,
            }
            for job in agent.active_jobs.values()
        ]
    }


# Shared result store: conversation_id → call result dict.
# Populated by the webhook, readable by agent polling as a secondary source.
call_results: dict[str, dict] = {}


def _detect_webhook_outcome(transcript, analysis: dict | None) -> str:
    """Light-weight outcome detection reused from agent module."""
    from .agent import _detect_booking_outcome

    transcript_text = ""
    if isinstance(transcript, list):
        for turn in transcript:
            role = turn.get("role", "unknown")
            msg = turn.get("message", "")
            transcript_text += f"{role}: {msg}\n"
    elif isinstance(transcript, str):
        transcript_text = transcript
    return _detect_booking_outcome(transcript_text, analysis or {})


# ElevenLabs webhook endpoint (post-call/status)
@app.post("/webhooks/elevenlabs")
async def elevenlabs_webhook(request: Request):
    """
    Receive ElevenLabs ConvAI/Twilio webhook callbacks.
    Extracts transcript, detects booking outcome, stores the result
    in the shared ``call_results`` dict, and optionally forwards to
    the web-app DB.
    """
    secret_expected = os.getenv("ELEVENLABS_WEBHOOK_SECRET")
    provided = (
        request.headers.get("x-elevenlabs-signature")
        or request.headers.get("x-webhook-secret")
    )

    if secret_expected:
        if not provided or provided != secret_expected:
            logger.warning("ElevenLabs webhook: bad/missing signature")
            raise HTTPException(status_code=401, detail="invalid secret")

    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid json: {e}")

    event_type = payload.get("type")
    event_timestamp = payload.get("event_timestamp")

    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if not data:
        data = payload
        if not event_type:
            event_type = "legacy"

    logger.info("ElevenLabs webhook type=%s", event_type)

    conversation_id = data.get("conversation_id") or data.get("conversationId")
    call_sid = data.get("callSid") or data.get("call_sid")
    status = data.get("status") or data.get("call_status")
    to_number = data.get("to") or data.get("to_number") or ""
    job_id = data.get("jobId") or data.get("job_id") or "unknown"
    full_audio = data.get("full_audio") or data.get("fullAudio")

    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else None
    transcript = data.get("transcript")
    summary = None
    if analysis:
        summary = analysis.get("transcript_summary") or analysis.get("summary")
    summary = summary or data.get("summary") or data.get("transcript_summary")

    if event_type == "post_call_audio" and not full_audio:
        raise HTTPException(status_code=400, detail="missing full_audio")

    outcome = _detect_webhook_outcome(transcript, analysis)

    from datetime import datetime as _dt
    call_result = {
        "conversation_id": conversation_id,
        "callSid": call_sid,
        "status": status,
        "summary": summary,
        "outcome": outcome,
        "to": to_number,
        "job_id": job_id,
        "type": event_type,
        "event_timestamp": event_timestamp,
        "received_at": _dt.utcnow().isoformat(),
        "analysis": analysis,
        "transcript": transcript,
        "full_audio": bool(full_audio),
    }

    # Store for agent polling
    if conversation_id:
        call_results[conversation_id] = call_result
    if call_sid:
        call_results[call_sid] = call_result

    logger.info(
        "Webhook stored: conv=%s outcome=%s summary=%s",
        conversation_id, outcome, (summary or "")[:80],
    )

    import hashlib
    storage_uri = None
    try:
        h = hashlib.sha256(
            json.dumps(call_result, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        storage_uri = f"ipfs://sota-call-{h}"
    except Exception:
        pass

    # Forward to web-app DB if configured
    calls_api = os.getenv("CALL_SUMMARY_WEBHOOK_URL")
    call_summary_secret = os.getenv("CALL_SUMMARY_SECRET") or secret_expected
    if calls_api:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    calls_api,
                    json={
                        "conversationId": conversation_id,
                        "callSid": call_sid,
                        "status": status,
                        "summary": summary,
                        "outcome": outcome,
                        "toNumber": to_number,
                        "jobId": str(job_id),
                        "storageUri": storage_uri,
                        "payload": payload,
                    },
                    headers={
                        "x-call-summary-secret": call_summary_secret or "",
                    },
                )
                if resp.status_code >= 300:
                    logger.warning(
                        "Failed to persist call summary: %s %s",
                        resp.status_code, resp.text[:200],
                    )
        except Exception as e:
            logger.warning("Error posting call summary: %s", e)

    return {
        "received": True,
        "conversation_id": conversation_id,
        "callSid": call_sid,
        "status": status,
        "outcome": outcome,
        "storage_uri": storage_uri,
    }


# Simple confirmation webhook → submitDelivery on-chain
class ConfirmationPayload(BaseModel):
    confirmation_number: str


@app.post("/webhooks/confirmation")
async def confirmation_webhook(payload: ConfirmationPayload):
    """
    Accept a confirmation_number and submit it as delivery proof.
    proof_hash = UTF-8 bytes of confirmation_number.
    """
    if not agent or not agent._contracts:
        raise HTTPException(status_code=503, detail="Agent or contracts not initialized")

    # Require exactly one active job to avoid ambiguity
    if not agent.active_jobs:
        raise HTTPException(status_code=404, detail="No active job to confirm")
    if len(agent.active_jobs) > 1:
        raise HTTPException(status_code=409, detail="Multiple active jobs; cannot infer job_id")

    active: ActiveJob = next(iter(agent.active_jobs.values()))
    job_id = active.job_id
    proof_bytes = payload.confirmation_number.encode("utf-8")

    try:
        tx_hash = submit_delivery(agent._contracts, job_id, proof_bytes)
        active.status = "completed"
        return {
            "submitted": True,
            "job_id": job_id,
            "tx_hash": tx_hash,
        }
    except Exception as e:
        logger.error(f"❌ submit_delivery failed for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"submit_delivery failed: {e}")


# A2A Endpoint

@app.post("/v1/rpc", response_model=A2AResponse)
async def handle_a2a_request(request: Request):
    """
    Main A2A RPC endpoint.
    """
    try:
        body = await request.json()
        message = A2AMessage(**body)
    except Exception as e:
        return create_error_response(
            0,
            A2AErrorCode.PARSE_ERROR,
            f"Invalid request: {e}"
        )
    
    # Verify signature if present
    if message.signature:
        is_valid, signer = verify_message(message)
        if not is_valid:
            return create_error_response(
                message.id,
                A2AErrorCode.SIGNATURE_INVALID,
                "Invalid message signature"

            )
        
        # Check message freshness
        if not is_message_fresh(message):
            return create_error_response(
                message.id,
                A2AErrorCode.MESSAGE_EXPIRED,
                "Message has expired"
            )
    
    # Route to appropriate handler
    if message.method == A2AMethod.PING.value:
        return create_success_response(message.id, {"status": "ok", "agent": "caller"})
    
    elif message.method == A2AMethod.GET_CAPABILITIES.value:
        caps = agent.get_status() if agent else {}
        return create_success_response(message.id, {
            "agent": "archive_caller",
            "capabilities": caps.get("capabilities", []),
            "supported_job_types": caps.get("supported_job_types", []),
        })
    
    elif message.method == A2AMethod.GET_STATUS.value:
        return create_success_response(message.id, agent.get_status() if agent else {})
    
    elif message.method == A2AMethod.EXECUTE_TASK.value:
        return await handle_task_execution(message)
    
    else:
        return create_error_response(
            message.id,
            A2AErrorCode.METHOD_NOT_FOUND,
            f"Method not found: {message.method}"
        )


async def handle_task_execution(message: A2AMessage) -> A2AResponse:
    """Handle task execution requests from Manager Agent"""
    global agent
    
    if not agent:
        return create_error_response(
            message.id,
            A2AErrorCode.INTERNAL_ERROR,
            "Agent not initialized"
        )
    
    params = message.params
    job_id = params.get("job_id")
    task_type = params.get("task_type")
    description = params.get("description", "")
    
    logger.info(f"📥 Received task: job_id={job_id}, type={task_type}")
    
    # Return acceptance - job will be executed via event listener
    return create_success_response(message.id, {
        "accepted": True,
        "job_id": job_id,
        "status": "queued"
    })


# Manual test endpoints

@app.post("/call")
async def manual_call(phone_number: str, script: str):
    """Manual call endpoint for testing"""
    if not agent or not agent.llm_agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    prompt = f"Call {phone_number} with this script: {script}"
    response = await agent.llm_agent.run(prompt)
    return {"response": response}


@app.post("/sms")
async def manual_sms(phone_number: str, message: str):
    """Manual SMS endpoint for testing"""
    if not agent or not agent.llm_agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    prompt = f"Send SMS to {phone_number}: {message}"
    response = await agent.llm_agent.run(prompt)
    return {"response": response}


def run_server():
    """Run the Caller Agent server"""
    port = int(os.getenv("CALLER_PORT", "3003"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run_server()

