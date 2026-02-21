"""Integration tests — real WebSocket SDK↔Hub communication."""

import asyncio
import json
import time

import httpx
import pytest
import websockets

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _register_msg(name="test-agent", tags=None):
    return json.dumps({
        "type": "register",
        "agent": {
            "name": name,
            "tags": tags or ["test"],
            "version": "1.0.0",
            "wallet_address": "",
            "capabilities": tags or ["test"],
        },
    })


async def _connect_and_register(ws_url, name="test-agent", tags=None):
    """Connect, register, return (ws, agent_id)."""
    ws = await websockets.connect(ws_url)
    await ws.send(_register_msg(name, tags))
    raw = await asyncio.wait_for(ws.recv(), timeout=5)
    msg = json.loads(raw)
    assert msg["type"] == "registered"
    return ws, msg["agent_id"]


async def _post_job(http_url, tags=None, budget=10.0, bid_window=2):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{http_url}/jobs", json={
            "description": "test job",
            "tags": tags or ["test"],
            "budget_usdc": budget,
            "deadline_ts": int(time.time()) + 3600,
            "poster": "0xPoster",
            "bid_window_seconds": bid_window,
        })
        assert resp.status_code == 200
        return resp.json()


# ── Connection & Registration ────────────────────────────────────────────────

class TestConnection:
    async def test_agent_connects_and_receives_registered(self, hub_server):
        ws, agent_id = await _connect_and_register(hub_server.ws_url)
        assert agent_id
        await ws.close()

    async def test_agent_appears_in_get_agents(self, hub_server):
        ws, agent_id = await _connect_and_register(hub_server.ws_url)
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/agents")
            data = resp.json()
            assert data["total"] >= 1
            agent_ids = [a["agent_id"] for a in data["agents"]]
            assert agent_id in agent_ids
        await ws.close()

    async def test_non_register_first_message_closes(self, hub_server):
        ws = await websockets.connect(hub_server.ws_url)
        await ws.send(json.dumps({"type": "bid", "job_id": "j1", "amount_usdc": 5}))
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        assert "error" in msg
        # Connection should be closed
        try:
            await asyncio.wait_for(ws.recv(), timeout=2)
        except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError):
            pass

    async def test_two_agents_connect(self, hub_server):
        ws1, id1 = await _connect_and_register(hub_server.ws_url, "agent-1")
        ws2, id2 = await _connect_and_register(hub_server.ws_url, "agent-2")
        assert id1 != id2
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/agents")
            assert resp.json()["total"] >= 2
        await ws1.close()
        await ws2.close()


# ── Job Broadcast & Bidding ──────────────────────────────────────────────────

class TestBidding:
    async def test_job_broadcast_to_matching(self, hub_server):
        ws, _ = await _connect_and_register(hub_server.ws_url, tags=["nlp"])
        job_resp = await _post_job(hub_server.http_url, tags=["nlp"], bid_window=2)
        assert job_resp["matched_agents"] >= 1

        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        assert msg["type"] == "job_available"
        assert msg["job"]["tags"] == ["nlp"]
        await ws.close()

    async def test_job_not_broadcast_to_non_matching(self, hub_server):
        ws, _ = await _connect_and_register(hub_server.ws_url, tags=["python"])
        await _post_job(hub_server.http_url, tags=["javascript"], bid_window=2)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.recv(), timeout=2)
        await ws.close()

    async def test_agent_bids_and_bid_appears(self, hub_server):
        ws, _ = await _connect_and_register(hub_server.ws_url, tags=["test"])
        job_resp = await _post_job(hub_server.http_url, tags=["test"], bid_window=3)
        job_id = job_resp["job_id"]

        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        assert msg["type"] == "job_available"

        # Send bid
        await ws.send(json.dumps({
            "type": "bid", "job_id": job_id, "amount_usdc": 8.0,
        }))

        # Wait a bit for bid processing
        await asyncio.sleep(0.5)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/jobs/{job_id}")
            data = resp.json()
            assert len(data["bids"]) >= 1

        await ws.close()

    async def test_two_agents_bid_lowest_wins(self, hub_server):
        ws1, _ = await _connect_and_register(hub_server.ws_url, "cheap", tags=["test"])
        ws2, _ = await _connect_and_register(hub_server.ws_url, "expensive", tags=["test"])

        job_resp = await _post_job(hub_server.http_url, tags=["test"], bid_window=2)
        job_id = job_resp["job_id"]

        # Both receive job
        raw1 = await asyncio.wait_for(ws1.recv(), timeout=5)
        raw2 = await asyncio.wait_for(ws2.recv(), timeout=5)

        # Both bid
        await ws1.send(json.dumps({"type": "bid", "job_id": job_id, "amount_usdc": 3.0}))
        await ws2.send(json.dumps({"type": "bid", "job_id": job_id, "amount_usdc": 8.0}))

        # Wait for bid window to close and results
        msgs1 = []
        msgs2 = []
        try:
            for _ in range(5):
                raw = await asyncio.wait_for(ws1.recv(), timeout=4)
                msgs1.append(json.loads(raw))
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            pass
        try:
            for _ in range(5):
                raw = await asyncio.wait_for(ws2.recv(), timeout=4)
                msgs2.append(json.loads(raw))
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            pass

        # Cheap agent should get bid_accepted
        types1 = [m["type"] for m in msgs1]
        types2 = [m["type"] for m in msgs2]
        assert "bid_accepted" in types1
        assert "bid_rejected" in types2

        await ws1.close()
        await ws2.close()

    async def test_no_bids_job_expires(self, hub_server):
        ws, _ = await _connect_and_register(hub_server.ws_url, tags=["test"])
        job_resp = await _post_job(hub_server.http_url, tags=["rare_tag"], bid_window=1)

        # Wait for bid window to close
        await asyncio.sleep(2)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/jobs/{job_resp['job_id']}")
            data = resp.json()
            assert data["status"] == "expired"
        await ws.close()


# ── Execution & Completion ───────────────────────────────────────────────────

class TestExecution:
    async def test_full_lifecycle(self, hub_server):
        ws, _ = await _connect_and_register(hub_server.ws_url, tags=["test"])
        job_resp = await _post_job(hub_server.http_url, tags=["test"], bid_window=2)
        job_id = job_resp["job_id"]

        # Receive job
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        assert msg["type"] == "job_available"

        # Bid
        await ws.send(json.dumps({"type": "bid", "job_id": job_id, "amount_usdc": 5.0}))

        # Wait for bid_accepted
        accepted = None
        for _ in range(10):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=4)
                m = json.loads(raw)
                if m.get("type") == "bid_accepted":
                    accepted = m
                    break
            except asyncio.TimeoutError:
                break
        assert accepted is not None

        # Complete the job
        await ws.send(json.dumps({
            "type": "job_completed", "job_id": job_id,
            "success": True, "result": {"answer": 42},
        }))

        await asyncio.sleep(0.5)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/jobs/{job_id}")
            data = resp.json()
            assert data["status"] == "completed"

        await ws.close()

    async def test_job_failed_marks_status(self, hub_server):
        ws, _ = await _connect_and_register(hub_server.ws_url, tags=["test"])
        job_resp = await _post_job(hub_server.http_url, tags=["test"], bid_window=2)
        job_id = job_resp["job_id"]

        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        await ws.send(json.dumps({"type": "bid", "job_id": job_id, "amount_usdc": 5.0}))

        for _ in range(10):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=4)
                m = json.loads(raw)
                if m.get("type") == "bid_accepted":
                    break
            except asyncio.TimeoutError:
                break

        await ws.send(json.dumps({
            "type": "job_failed", "job_id": job_id, "error": "test error",
        }))

        await asyncio.sleep(0.5)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{hub_server.http_url}/jobs/{job_id}")
            data = resp.json()
            assert data["status"] == "failed"

        await ws.close()


# ── Heartbeat & Edge Cases ───────────────────────────────────────────────────

class TestEdgeCases:
    async def test_heartbeat_updates_timestamp(self, hub_server):
        ws, agent_id = await _connect_and_register(hub_server.ws_url)
        agent = hub_server.registry.get(agent_id)
        old_hb = agent.last_heartbeat

        await asyncio.sleep(0.05)
        await ws.send(json.dumps({"type": "heartbeat"}))
        await asyncio.sleep(0.1)

        agent = hub_server.registry.get(agent_id)
        assert agent.last_heartbeat > old_hb
        await ws.close()

    async def test_malformed_json_ignored(self, hub_server):
        ws, _ = await _connect_and_register(hub_server.ws_url)
        await ws.send("not json at all {{{{")
        # Should not disconnect — send a heartbeat to prove still alive
        await asyncio.sleep(0.1)
        await ws.send(json.dumps({"type": "heartbeat"}))
        # If we got here without exception, connection is still alive
        await ws.close()
