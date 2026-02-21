"""
incident.io Client — Async API wrapper for Alert Events V2, Incidents V2, Schedules V2.

Graceful degradation: if ``INCIDENT_IO_API_KEY`` is not set, ``from_env()``
returns ``None`` and all methods become unreachable.  Callers should guard
with ``if client:`` before calling.

Rate limit: 1200 req/min (incident.io default).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.incident.io"
ALERT_EVENTS_URL = "https://api.incident.io/v2/alert_events/http"

SEVERITY_MAP_DEFAULT: Dict[str, str] = {
    "critical": "01HWTHZGQ1GQKBWNYV3HKG3K5V",
    "high": "01HWTHZGQ1GQKBWNYV3HKG3K5W",
    "medium": "01HWTHZGQ1GQKBWNYV3HKG3K5X",
    "low": "01HWTHZGQ1GQKBWNYV3HKG3K5Y",
}


class IncidentIOClient:
    """Async httpx wrapper around incident.io's public API."""

    def __init__(
        self,
        api_key: str,
        alert_source_id: str,
        *,
        severity_map: Dict[str, str] | None = None,
        timeout: float = 15.0,
    ):
        self.api_key = api_key
        self.alert_source_id = alert_source_id
        self.severity_map = severity_map or SEVERITY_MAP_DEFAULT
        self._timeout = timeout

    # ── Factory ──────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> Optional["IncidentIOClient"]:
        """Return a configured client, or ``None`` if credentials are missing."""
        api_key = os.getenv("INCIDENT_IO_API_KEY", "").strip()
        alert_source_id = os.getenv("INCIDENT_IO_ALERT_SOURCE_ID", "").strip()

        if not api_key:
            logger.info("INCIDENT_IO_API_KEY not set — incident.io integration disabled")
            return None

        sev_env = os.getenv("INCIDENT_IO_SEVERITY_MAP", "").strip()
        sev_map = None
        if sev_env:
            try:
                import json
                sev_map = json.loads(sev_env)
            except Exception:
                logger.warning("Could not parse INCIDENT_IO_SEVERITY_MAP — using defaults")

        return cls(api_key=api_key, alert_source_id=alert_source_id, severity_map=sev_map)

    # ── Helpers ──────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _severity_id(self, level: str) -> str | None:
        return self.severity_map.get(level)

    # ── Alert Events V2 ─────────────────────────────────────

    async def create_alert(
        self,
        title: str,
        description: str = "",
        *,
        metadata: Dict[str, Any] | None = None,
        dedup_key: str = "",
        status: str = "firing",
        severity: str = "high",
        source_url: str = "",
    ) -> Dict[str, Any] | None:
        """
        POST /v2/alert_events/http/{alert_source_config_id}

        Fires (or resolves) an alert.  If ``alert_source_id`` is empty,
        falls back to Incidents V2 ``create_incident`` for direct creation.
        """
        if not self.alert_source_id:
            logger.debug("No alert_source_id — creating incident directly instead")
            if status == "firing":
                return await self.create_incident(
                    name=title, summary=description, severity=severity,
                )
            return None

        url = f"{ALERT_EVENTS_URL}/{self.alert_source_id}"
        payload: Dict[str, Any] = {
            "dedup_key": dedup_key or title[:128],
            "title": title[:512],
            "description": description[:4096],
            "status": status,
            "metadata": metadata or {},
        }
        if source_url:
            payload["source_url"] = source_url

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                logger.info(
                    "incident.io alert %s: dedup=%s status=%s",
                    "created" if status == "firing" else "resolved",
                    dedup_key, status,
                )
                return data
        except Exception as exc:
            logger.warning("incident.io create_alert failed: %s", exc)
            return None

    async def resolve_alert(self, dedup_key: str) -> Dict[str, Any] | None:
        """Convenience: resolve a previously-fired alert by its dedup key."""
        return await self.create_alert(
            title="Resolved",
            dedup_key=dedup_key,
            status="resolved",
        )

    # ── Incidents V2 ─────────────────────────────────────────

    async def create_incident(
        self,
        name: str,
        summary: str = "",
        severity: str = "high",
        *,
        custom_fields: Dict[str, Any] | None = None,
        idempotency_key: str = "",
    ) -> Dict[str, Any] | None:
        """POST /v2/incidents"""
        url = f"{BASE_URL}/v2/incidents"
        body: Dict[str, Any] = {
            "incident": {
                "name": name[:512],
                "summary": summary[:4096],
                "idempotency_key": idempotency_key or name[:128],
            },
            "visibility": "public",
        }
        sev_id = self._severity_id(severity)
        if sev_id:
            body["incident"]["severity_id"] = sev_id
        if custom_fields:
            body["incident"]["custom_field_entries"] = [
                {"custom_field_id": k, "value": v}
                for k, v in custom_fields.items()
            ]

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=body, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                logger.info("incident.io incident created: %s", data.get("incident", {}).get("id"))
                return data
        except Exception as exc:
            logger.warning("incident.io create_incident failed: %s", exc)
            return None

    async def update_incident(
        self,
        incident_id: str,
        *,
        summary: str | None = None,
        status_id: str | None = None,
    ) -> Dict[str, Any] | None:
        """POST /v2/incidents/{id}/actions/edit"""
        url = f"{BASE_URL}/v2/incidents/{incident_id}/actions/edit"
        body: Dict[str, Any] = {"incident": {}}
        if summary is not None:
            body["incident"]["summary"] = summary[:4096]
        if status_id is not None:
            body["incident"]["status_id"] = status_id
        if not body["incident"]:
            return None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=body, headers=self._headers())
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("incident.io update_incident failed: %s", exc)
            return None

    async def list_incidents(
        self,
        *,
        status_category: str | None = None,
        severity: str | None = None,
        page_size: int = 25,
    ) -> List[Dict[str, Any]]:
        """GET /v2/incidents with optional filters."""
        url = f"{BASE_URL}/v2/incidents"
        params: Dict[str, Any] = {"page_size": page_size}
        if status_category:
            params["status_category[one_of]"] = status_category
        sev_id = self._severity_id(severity) if severity else None
        if sev_id:
            params["severity[one_of]"] = sev_id

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return data.get("incidents", [])
        except Exception as exc:
            logger.warning("incident.io list_incidents failed: %s", exc)
            return []

    # ── Schedules V2 ─────────────────────────────────────────

    async def get_on_call(self, schedule_id: str) -> Dict[str, Any] | None:
        """GET /v2/schedules/{id} — returns current on-call info."""
        url = f"{BASE_URL}/v2/schedules/{schedule_id}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=self._headers())
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("incident.io get_on_call failed: %s", exc)
            return None
