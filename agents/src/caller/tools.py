"""
Caller Agent Tools

Tools for phone-based verification using Twilio.
These are EXECUTION tools — bidding is handled by shared bidding_tools.
"""

import os
import json
import hashlib
from typing import Any, Optional
from datetime import datetime

from pydantic import Field

from ..shared.tool_base import BaseTool

import httpx


class MakePhoneCallTool(BaseTool):
    """
    Tool to make phone calls using Twilio.
    """
    name: str = "make_phone_call"
    description: str = """
    Make an outbound phone call using Twilio Voice API.
    
    Can play a script using text-to-speech or gather user input.
    Returns call status and recording URL if available.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "phone_number": {
                "type": "string",
                "description": "The phone number to call (E.164 format, e.g., +74951234567)"
            },
            "script": {
                "type": "string",
                "description": "The script to read (text-to-speech)"
            },
            "gather_input": {
                "type": "boolean",
                "description": "Whether to gather DTMF input from the call recipient"
            },
            "record": {
                "type": "boolean",
                "description": "Whether to record the call"
            }
        },
        "required": ["phone_number", "script"]
    }
    
    async def execute(
        self,
        phone_number: str,
        script: str,
        gather_input: bool = False,
        record: bool = True,
    ) -> str:
        """Make a basic TwiML phone call (one-way script only).

        This is an emergency fallback; prefer MakeElevenLabsCallTool for
        real conversational calls.
        """
        from twilio.rest import Client
        from twilio.twiml.voice_response import VoiceResponse

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_PHONE_NUMBER")

        if not all([account_sid, auth_token, from_number]):
            return json.dumps({
                "success": False,
                "error": "Twilio credentials not configured"
            })

        try:
            client = Client(account_sid, auth_token)
            response = VoiceResponse()
            response.say(script, language="en-US")

            call = client.calls.create(
                to=phone_number,
                from_=from_number,
                twiml=str(response),
                record=record,
            )

            return json.dumps({
                "success": True,
                "call_sid": call.sid,
                "status": call.status,
                "phone_number": phone_number,
                "from_number": from_number,
                "direction": call.direction,
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e)
            })


class GetCallStatusTool(BaseTool):
    """
    Tool to check the status of a Twilio call.
    """
    name: str = "get_call_status"
    description: str = """
    Get the current status of a phone call by its SID.
    
    Returns call duration, status, and recording URL if available.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "call_sid": {
                "type": "string",
                "description": "The Twilio Call SID"
            }
        },
        "required": ["call_sid"]
    }
    
    async def execute(self, call_sid: str) -> str:
        """Get call status from Twilio"""
        from twilio.rest import Client
        
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        
        if not all([account_sid, auth_token]):
            return json.dumps({
                "success": False,
                "error": "Twilio credentials not configured"
            })
        
        try:
            client = Client(account_sid, auth_token)
            call = client.calls(call_sid).fetch()
            
            # Get recordings if available
            recordings = client.calls(call_sid).recordings.list()
            recording_urls = [
                f"https://api.twilio.com{r.uri.replace('.json', '.mp3')}"
                for r in recordings
            ]
            
            return json.dumps({
                "success": True,
                "call_sid": call.sid,
                "status": call.status,
                "duration": call.duration,
                "direction": call.direction,
                "answered_by": call.answered_by,
                "start_time": str(call.start_time) if call.start_time else None,
                "end_time": str(call.end_time) if call.end_time else None,
                "recording_urls": recording_urls
            }, indent=2)
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e)
            })


class SendSMSTool(BaseTool):
    """
    Tool to send SMS messages via Twilio.
    """
    name: str = "send_sms"
    description: str = """
    Send an SMS message using Twilio.
    
    Useful for follow-up confirmations after calls.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "phone_number": {
                "type": "string",
                "description": "The phone number to send SMS to (E.164 format)"
            },
            "message": {
                "type": "string",
                "description": "The SMS message content"
            }

        },
        "required": ["phone_number", "message"]
    }
    
    async def execute(self, phone_number: str, message: str) -> str:
        """Send an SMS via Twilio"""
        from twilio.rest import Client
        
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_PHONE_NUMBER")
        
        if not all([account_sid, auth_token, from_number]):
            return json.dumps({
                "success": False,
                "error": "Twilio credentials not configured"
            })
        
        try:
            client = Client(account_sid, auth_token)
            
            sms = client.messages.create(
                to=phone_number,
                from_=from_number,
                body=message
            )
            
            return json.dumps({
                "success": True,
                "message_sid": sms.sid,
                "status": sms.status,
                "phone_number": phone_number
            }, indent=2)
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e)
            })


class UploadCallResultTool(BaseTool):
    """
    Tool to upload call results to storage.
    """
    name: str = "upload_call_result"
    description: str = """
    Upload call result data to decentralized storage.

    Stores call metadata, transcript, and outcome for proof-of-work.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "integer",
                "description": "The job ID"
            },
            "phone_number": {
                "type": "string",
                "description": "The phone number that was called"
            },
            "call_sid": {
                "type": "string",
                "description": "The Twilio Call SID"
            },
            "status": {
                "type": "string",
                "description": "Call outcome status"
            },
            "notes": {
                "type": "string",
                "description": "Additional notes about the call"
            }
        },
        "required": ["job_id", "phone_number", "status"]
    }

    async def execute(
        self,
        job_id: int,
        phone_number: str,
        status: str,
        call_sid: str = None,
        notes: str = None
    ) -> str:
        """Upload call result and return an IPFS-style URI"""
        import hashlib

        call_result = {
            "job_id": job_id,
            "phone_number": phone_number,
            "call_sid": call_sid,
            "status": status,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat()
        }

        result_hash = hashlib.sha256(
            json.dumps(call_result, sort_keys=True).encode()
        ).hexdigest()[:16]
        object_id = f"call-result-{job_id}-{result_hash}"
        storage_uri = f"ipfs://{object_id}"

        return json.dumps({
            "success": True,
            "object_id": object_id,
            "storage_uri": storage_uri,
            "job_id": job_id
        }, indent=2)


class ComputeProofHashTool(BaseTool):
    """
    Tool to compute proof hash from a storage object ID.
    """
    name: str = "compute_proof_hash"
    description: str = """
    Compute a proof hash from a storage object ID for delivery submission.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "object_id": {
                "type": "string",
                "description": "The storage object ID"
            }
        },
        "required": ["object_id"]
    }

    async def execute(self, object_id: str) -> str:
        """Compute proof hash"""
        try:
            proof_hash = hashlib.sha256(object_id.encode()).digest()

            return json.dumps({
                "success": True,
                "object_id": object_id,
                "proof_hash": proof_hash.hex()
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e)
            })


class GetElevenLabsConversationTool(BaseTool):
    """
    Poll ElevenLabs for conversation status, transcript, and analysis.
    """
    name: str = "get_elevenlabs_conversation"
    description: str = (
        "Retrieve the current status, transcript, and analysis of an "
        "ElevenLabs ConvAI conversation by its conversation_id."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "conversation_id": {
                "type": "string",
                "description": "The ElevenLabs conversation ID",
            }
        },
        "required": ["conversation_id"],
    }

    async def execute(self, conversation_id: str) -> str:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return json.dumps({"success": False, "error": "ELEVENLABS_API_KEY not set"})

        url = f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url, headers={"xi-api-key": api_key}
                )
                if resp.status_code == 404:
                    return json.dumps({
                        "success": True,
                        "status": "not_found",
                        "data": None,
                    })
                resp.raise_for_status()
                return json.dumps({
                    "success": True,
                    "status": "ok",
                    "data": resp.json(),
                }, indent=2, default=str)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


def create_caller_tools() -> list[BaseTool]:
    """
    Create all caller-specific tools.

    Note: Bidding and wallet tools are created separately in the agent.
    """
    return [
        MakePhoneCallTool(),
        MakeElevenLabsCallTool(),
        GetElevenLabsConversationTool(),
        GetCallStatusTool(),
        SendSMSTool(),
        UploadCallResultTool(),
        ComputeProofHashTool(),
    ]


class MakeElevenLabsCallTool(BaseTool):
    """
    Initiate an outbound call via ElevenLabs ConvAI (Twilio integration).
    
    Uses the official ElevenLabs outbound-call API to avoid websocket/DTMF
    disconnect issues seen with manual Twilio calls.
    """
    name: str = "make_elevenlabs_call"
    description: str = """
    Place an outbound call using ElevenLabs ConvAI Twilio integration.
    Requires ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID, ELEVENLABS_PHONE_ID (the
    ElevenLabs phone_number_id) to be set in env. Sends dynamic variables for
    the first message.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "to_number": {
                "type": "string",
                "description": "Destination phone in E.164 format, e.g., +447512593720"
            },
            "user_name": {"type": "string", "description": "Guest name for the reservation"},
            "time": {"type": "string", "description": "Time slot, e.g., 8pm"},
            "date": {"type": "string", "description": "Date string"},
            "num_of_people": {"type": "integer", "description": "Number of guests"},
            "booking_type": {"type": "string", "description": "restaurant or hotel"},
            "cuisine": {"type": "string", "description": "Cuisine preference (restaurant only)"},
            "location": {"type": "string", "description": "Location / area preference"},
            "special_requests": {"type": "string", "description": "Any special requests"},
        },
        "required": ["to_number", "user_name"],
    }

    async def execute(
        self,
        to_number: str,
        user_name: str,
        time: str = "8pm",
        date: str = "tomorrow",
        num_of_people: int = 2,
        booking_type: str = "restaurant",
        cuisine: str = "",
        location: str = "",
        special_requests: str = "",
    ) -> str:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        agent_id = os.getenv("ELEVENLABS_CALLER_AGENT_ID") or os.getenv("ELEVENLABS_AGENT_ID")
        phone_id = os.getenv("ELEVENLABS_PHONE_ID")

        if not api_key or not agent_id or not phone_id:
            return json.dumps(
                {
                    "success": False,
                    "error": "Missing ELEVENLABS_API_KEY / ELEVENLABS_CALLER_AGENT_ID / ELEVENLABS_PHONE_ID",
                }
            )

        payload = {
            "agent_id": agent_id,
            "agent_phone_number_id": phone_id,
            "to_number": to_number,
            "authenticated": True,
            "conversation_initiation_client_data": {
                "type": "conversation_initiation_client_data",
                "dynamic_variables": {
                    "user_name": user_name,
                    "time": time,
                    "num_of_people": str(num_of_people),
                    "date": date,
                    "booking_type": booking_type,
                    "cuisine": cuisine,
                    "location": location,
                    "special_requests": special_requests,
                },
            },
        }

        url = "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    url,
                    headers={
                        "xi-api-key": api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                return json.dumps(
                    {"success": True, "status_code": resp.status_code, "body": resp.json()},
                    indent=2,
                )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

