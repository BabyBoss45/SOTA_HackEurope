"""
Incident Tools — BaseTool subclasses for incident.io operations.

Gives the Butler (or any LLM agent) the ability to create, query,
update, and resolve incidents via conversation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import Field

from .tool_base import BaseTool

logger = logging.getLogger(__name__)

# Singleton reference — set at startup from butler_api.py
_incident_io_client: Any = None


def set_incident_io_client(client: Any) -> None:
    """Called once at startup to inject the shared IncidentIOClient."""
    global _incident_io_client
    _incident_io_client = client


def _client():
    return _incident_io_client


# ── Create Incident ──────────────────────────────────────────

class CreateIncidentTool(BaseTool):
    name: str = "create_incident"
    description: str = (
        "Create a new incident on incident.io with a name, summary, and severity. "
        "Use when an agent or user wants to manually flag a problem."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short incident title (e.g. 'Hackathon registration failing')",
            },
            "summary": {
                "type": "string",
                "description": "Longer description of the incident",
            },
            "severity": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low"],
                "description": "Severity level",
            },
        },
        "required": ["name"],
    }

    async def execute(
        self,
        name: str,
        summary: str = "",
        severity: str = "high",
        **kwargs: Any,
    ) -> str:
        client = _client()
        if not client:
            return json.dumps({"success": False, "error": "incident.io not configured"})
        result = await client.create_incident(
            name=name, summary=summary, severity=severity,
        )
        if result:
            incident_id = result.get("incident", {}).get("id", "unknown")
            return json.dumps({
                "success": True,
                "incident_id": incident_id,
                "message": f"Incident '{name}' created (severity={severity})",
            })
        return json.dumps({"success": False, "error": "Failed to create incident"})


# ── Query Incidents ──────────────────────────────────────────

class QueryIncidentsTool(BaseTool):
    name: str = "query_incidents"
    description: str = (
        "List open or active incidents from incident.io. "
        "Optionally filter by status category (e.g. 'active', 'closed') or severity."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "status_category": {
                "type": "string",
                "description": "Filter: 'active', 'closed', 'post_incident', etc.",
            },
            "severity": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low"],
                "description": "Filter by severity level",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        status_category: str | None = None,
        severity: str | None = None,
        **kwargs: Any,
    ) -> str:
        client = _client()
        if not client:
            return json.dumps({"success": False, "error": "incident.io not configured"})
        incidents = await client.list_incidents(
            status_category=status_category, severity=severity,
        )
        summaries = []
        for inc in incidents[:10]:
            summaries.append({
                "id": inc.get("id"),
                "name": inc.get("name"),
                "status": inc.get("incident_status", {}).get("name"),
                "severity": inc.get("severity", {}).get("name"),
                "created_at": inc.get("created_at"),
            })
        return json.dumps({
            "success": True,
            "count": len(incidents),
            "incidents": summaries,
        })


# ── Update Incident ──────────────────────────────────────────

class UpdateIncidentTool(BaseTool):
    name: str = "update_incident"
    description: str = (
        "Update an existing incident's summary or status on incident.io."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "incident_id": {
                "type": "string",
                "description": "The incident.io incident ID",
            },
            "summary": {
                "type": "string",
                "description": "Updated summary text",
            },
            "status_id": {
                "type": "string",
                "description": "New status ID (from incident.io)",
            },
        },
        "required": ["incident_id"],
    }

    async def execute(
        self,
        incident_id: str,
        summary: str | None = None,
        status_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        client = _client()
        if not client:
            return json.dumps({"success": False, "error": "incident.io not configured"})
        result = await client.update_incident(
            incident_id=incident_id, summary=summary, status_id=status_id,
        )
        if result:
            return json.dumps({"success": True, "message": f"Incident {incident_id} updated"})
        return json.dumps({"success": False, "error": "Update failed or no changes"})


# ── Resolve Alert ────────────────────────────────────────────

class ResolveAlertTool(BaseTool):
    name: str = "resolve_alert"
    description: str = (
        "Manually resolve an alert on incident.io by its dedup key. "
        "SOTA alerts use the pattern 'sota-job-{job_id}'."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "dedup_key": {
                "type": "string",
                "description": "Dedup key of the alert to resolve (e.g. 'sota-job-42')",
            },
        },
        "required": ["dedup_key"],
    }

    async def execute(self, dedup_key: str, **kwargs: Any) -> str:
        client = _client()
        if not client:
            return json.dumps({"success": False, "error": "incident.io not configured"})
        result = await client.resolve_alert(dedup_key=dedup_key)
        if result:
            return json.dumps({"success": True, "message": f"Alert '{dedup_key}' resolved"})
        return json.dumps({"success": False, "error": "Resolve failed"})


# ── Check On-Call ────────────────────────────────────────────

class CheckOnCallTool(BaseTool):
    name: str = "check_on_call"
    description: str = (
        "Check who is currently on-call for a given incident.io schedule. "
        "Useful for escalation decisions."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "schedule_id": {
                "type": "string",
                "description": "The incident.io schedule ID to query",
            },
        },
        "required": ["schedule_id"],
    }

    async def execute(self, schedule_id: str, **kwargs: Any) -> str:
        client = _client()
        if not client:
            return json.dumps({"success": False, "error": "incident.io not configured"})
        result = await client.get_on_call(schedule_id=schedule_id)
        if result:
            return json.dumps({"success": True, "schedule": result})
        return json.dumps({"success": False, "error": "Could not fetch on-call info"})


# ── Factory ──────────────────────────────────────────────────

def create_incident_tools() -> list[BaseTool]:
    """Return all incident.io tools for registration in a ToolManager."""
    return [
        CreateIncidentTool(),
        QueryIncidentsTool(),
        UpdateIncidentTool(),
        ResolveAlertTool(),
        CheckOnCallTool(),
    ]
