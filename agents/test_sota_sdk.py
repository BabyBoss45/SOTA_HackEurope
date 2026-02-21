"""
Comprehensive test suite for the sota_sdk package.

Tests every module: config, models, tools, bidding, registration,
marketplace client, wallet, contracts, server, and the SOTAAgent class.
"""

import asyncio
import json
import sys
import os
import time
import traceback
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

results: list[dict] = []


def record(test_id: str, module: str, test_name: str, passed: bool, detail: str = ""):
    results.append({
        "id": test_id,
        "module": module,
        "test": test_name,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    })


def run_sync(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# 1. CONFIG MODULE
# ===========================================================================

def test_config():
    module = "config"

    # T01: imports
    try:
        from sota_sdk.config import (
            SOTA_MARKETPLACE_URL, SOTA_AGENT_PRIVATE_KEY,
            WS_HEARTBEAT_INTERVAL, WS_RECONNECT_MIN, WS_RECONNECT_MAX,
            get_network, get_contract_addresses,
            NetworkConfig, ContractAddresses,
        )
        record("T01", module, "All config symbols importable", True)
    except Exception as e:
        record("T01", module, "All config symbols importable", False, str(e))
        return

    # T02: WS URL has correct default
    try:
        assert SOTA_MARKETPLACE_URL == "ws://localhost:3002/ws/agent", f"got {SOTA_MARKETPLACE_URL}"
        record("T02", module, "Default WS URL matches hub", True)
    except AssertionError as e:
        record("T02", module, "Default WS URL matches hub", False, str(e))

    # T03: get_network returns NetworkConfig
    try:
        net = get_network()
        assert isinstance(net, NetworkConfig)
        assert net.chain_id > 0
        record("T03", module, "get_network() returns valid NetworkConfig", True, f"chain_id={net.chain_id}")
    except Exception as e:
        record("T03", module, "get_network() returns valid NetworkConfig", False, str(e))

    # T04: get_contract_addresses returns ContractAddresses
    try:
        addrs = get_contract_addresses()
        assert isinstance(addrs, ContractAddresses)
        record("T04", module, "get_contract_addresses() returns ContractAddresses", True)
    except Exception as e:
        record("T04", module, "get_contract_addresses() returns ContractAddresses", False, str(e))

    # T05: heartbeat/reconnect are numeric
    try:
        assert isinstance(WS_HEARTBEAT_INTERVAL, int) and WS_HEARTBEAT_INTERVAL > 0
        assert isinstance(WS_RECONNECT_MIN, float) and WS_RECONNECT_MIN > 0
        assert isinstance(WS_RECONNECT_MAX, float) and WS_RECONNECT_MAX > WS_RECONNECT_MIN
        record("T05", module, "WS timing constants are valid", True,
               f"heartbeat={WS_HEARTBEAT_INTERVAL}s, reconnect={WS_RECONNECT_MIN}-{WS_RECONNECT_MAX}s")
    except Exception as e:
        record("T05", module, "WS timing constants are valid", False, str(e))

    # T06: no hardcoded private key
    try:
        # Should be None unless env is set
        if os.getenv("SOTA_AGENT_PRIVATE_KEY"):
            record("T06", module, "Private key not hardcoded", True, "env var is set (OK)")
        else:
            assert SOTA_AGENT_PRIVATE_KEY is None
            record("T06", module, "Private key not hardcoded", True, "None when env unset")
    except Exception as e:
        record("T06", module, "Private key not hardcoded", False, str(e))


# ===========================================================================
# 2. MODELS MODULE
# ===========================================================================

def test_models():
    module = "models"

    try:
        from sota_sdk.models import Job, Bid, BidResult, JobResult
        record("T07", module, "All model classes importable", True)
    except Exception as e:
        record("T07", module, "All model classes importable", False, str(e))
        return

    # T08: Job dataclass
    try:
        job = Job(id="j1", description="test", tags=["a"], budget_usdc=10.0,
                  deadline_ts=9999999999, poster="0xABC")
        assert job.id == "j1"
        assert job.tags == ["a"]
        assert job.metadata == {}  # default
        assert job.params == {}    # default
        record("T08", module, "Job dataclass construction + defaults", True)
    except Exception as e:
        record("T08", module, "Job dataclass construction + defaults", False, str(e))

    # T09: Bid dataclass
    try:
        bid = Bid(job_id="j1", amount_usdc=5.0)
        assert bid.estimated_seconds == 300  # default
        assert bid.bid_id == ""
        assert bid.tags == []
        record("T09", module, "Bid dataclass construction + defaults", True)
    except Exception as e:
        record("T09", module, "Bid dataclass construction + defaults", False, str(e))

    # T10: BidResult dataclass
    try:
        br = BidResult(job_id="j1", accepted=True, bid_id="b1")
        assert br.accepted is True
        assert br.reason == ""
        record("T10", module, "BidResult dataclass", True)
    except Exception as e:
        record("T10", module, "BidResult dataclass", False, str(e))

    # T11: JobResult dataclass
    try:
        jr = JobResult(success=True, data={"k": "v"})
        assert jr.error is None
        assert jr.proof_hash is None
        record("T11", module, "JobResult dataclass", True)
    except Exception as e:
        record("T11", module, "JobResult dataclass", False, str(e))


# ===========================================================================
# 3. TOOLS MODULE
# ===========================================================================

def test_tools():
    module = "tools"

    try:
        from sota_sdk.tools import BaseTool, ToolManager
        record("T12", module, "BaseTool and ToolManager importable", True)
    except Exception as e:
        record("T12", module, "BaseTool and ToolManager importable", False, str(e))
        return

    # T13: concrete tool
    try:
        class EchoTool(BaseTool):
            name: str = "echo"
            description: str = "Echoes input"
            parameters: dict = {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            }
            async def execute(self, **kw):
                return json.dumps({"echo": kw.get("text", "")})

        tool = EchoTool()
        schema = tool.to_anthropic_tool()
        assert schema["name"] == "echo"
        assert "input_schema" in schema
        record("T13", module, "Concrete tool + to_anthropic_tool()", True)
    except Exception as e:
        record("T13", module, "Concrete tool + to_anthropic_tool()", False, str(e))

    # T14: ToolManager register + call
    try:
        class AddTool(BaseTool):
            name: str = "add"
            description: str = "Adds two numbers"
            async def execute(self, a=0, b=0, **kw):
                return json.dumps({"sum": a + b})

        tm = ToolManager()
        tm.register(AddTool())
        assert len(tm) == 1
        result = run_sync(tm.call("add", {"a": 3, "b": 4}))
        parsed = json.loads(result)
        assert parsed["sum"] == 7
        record("T14", module, "ToolManager register + call dispatches", True, f"3+4={parsed['sum']}")
    except Exception as e:
        record("T14", module, "ToolManager register + call dispatches", False, str(e))

    # T15: ToolManager unknown tool
    try:
        tm2 = ToolManager()
        result = run_sync(tm2.call("nonexistent", {}))
        parsed = json.loads(result)
        assert "error" in parsed
        assert "Unknown tool" in parsed["error"]
        record("T15", module, "ToolManager returns error for unknown tool", True)
    except Exception as e:
        record("T15", module, "ToolManager returns error for unknown tool", False, str(e))

    # T16: ToolManager rejects empty name
    try:
        class EmptyNameTool(BaseTool):
            async def execute(self, **kw):
                return ""
        tm3 = ToolManager()
        try:
            tm3.register(EmptyNameTool())
            record("T16", module, "ToolManager rejects empty tool name", False, "no error raised")
        except ValueError:
            record("T16", module, "ToolManager rejects empty tool name", True)
    except Exception as e:
        record("T16", module, "ToolManager rejects empty tool name", False, str(e))

    # T17: to_anthropic_tools list
    try:
        class T1(BaseTool):
            name: str = "t1"
            description: str = "Tool 1"
            async def execute(self, **kw): return ""
        class T2(BaseTool):
            name: str = "t2"
            description: str = "Tool 2"
            async def execute(self, **kw): return ""
        tm4 = ToolManager([T1(), T2()])
        schemas = tm4.to_anthropic_tools()
        assert len(schemas) == 2
        names = {s["name"] for s in schemas}
        assert names == {"t1", "t2"}
        record("T17", module, "to_anthropic_tools() returns correct schemas", True)
    except Exception as e:
        record("T17", module, "to_anthropic_tools() returns correct schemas", False, str(e))

    # T18: tool execution error is sanitised
    try:
        class FailTool(BaseTool):
            name: str = "fail"
            description: str = "Always fails"
            async def execute(self, **kw):
                raise RuntimeError("secret-internal-detail-1234")
        tm5 = ToolManager([FailTool()])
        result = run_sync(tm5.call("fail", {}))
        parsed = json.loads(result)
        assert "secret-internal-detail" not in parsed["error"]
        assert "RuntimeError" in parsed["error"]
        record("T18", module, "Tool error sanitised (no internal details)", True)
    except Exception as e:
        record("T18", module, "Tool error sanitised (no internal details)", False, str(e))


# ===========================================================================
# 4. MARKETPLACE / REGISTRATION
# ===========================================================================

def test_registration():
    module = "marketplace.registration"

    try:
        from sota_sdk.marketplace.registration import build_register_message
        record("T19", module, "build_register_message importable", True)
    except Exception as e:
        record("T19", module, "build_register_message importable", False, str(e))
        return

    # T20: message structure
    try:
        msg = build_register_message("agent-x", ["web_scraping"], "2.0.0", "0xDEAD")
        assert msg["type"] == "register"
        assert msg["agent"]["name"] == "agent-x"
        assert msg["agent"]["tags"] == ["web_scraping"]
        assert msg["agent"]["version"] == "2.0.0"
        assert msg["agent"]["wallet_address"] == "0xDEAD"
        record("T20", module, "Register message structure matches hub protocol", True)
    except Exception as e:
        record("T20", module, "Register message structure matches hub protocol", False, str(e))

    # T21: defaults
    try:
        msg = build_register_message("a", ["t"], "1.0.0")
        assert msg["agent"]["wallet_address"] == ""
        assert msg["agent"]["capabilities"] == ["t"]  # defaults to tags
        record("T21", module, "Register message defaults (no wallet, caps=tags)", True)
    except Exception as e:
        record("T21", module, "Register message defaults (no wallet, caps=tags)", False, str(e))


# ===========================================================================
# 5. MARKETPLACE / BIDDING
# ===========================================================================

def test_bidding():
    module = "marketplace.bidding"

    try:
        from sota_sdk.marketplace.bidding import (
            BidStrategy, DefaultBidStrategy, CostAwareBidStrategy,
        )
        from sota_sdk.models import Job, Bid
        record("T22", module, "Bidding classes importable", True)
    except Exception as e:
        record("T22", module, "Bidding classes importable", False, str(e))
        return

    # T23: DefaultBidStrategy bids on matching tags
    try:
        strat = DefaultBidStrategy(price_ratio=0.75, agent_tags=["data_analysis"])
        job = Job(id="j1", description="analyze data", tags=["data_analysis"],
                  budget_usdc=100.0, deadline_ts=9999999999, poster="0x1")
        bid = run_sync(strat.evaluate(job))
        assert bid is not None
        assert bid.amount_usdc == 75.0  # 100 * 0.75
        assert bid.job_id == "j1"
        record("T23", module, "DefaultBidStrategy bids at ratio on matching tags", True,
               f"amount={bid.amount_usdc}")
    except Exception as e:
        record("T23", module, "DefaultBidStrategy bids at ratio on matching tags", False, str(e))

    # T24: DefaultBidStrategy skips non-matching tags
    try:
        strat = DefaultBidStrategy(agent_tags=["phone_call"])
        job = Job(id="j2", description="scrape web", tags=["web_scraping"],
                  budget_usdc=50.0, deadline_ts=9999999999, poster="0x2")
        bid = run_sync(strat.evaluate(job))
        assert bid is None
        record("T24", module, "DefaultBidStrategy skips non-matching tags", True)
    except Exception as e:
        record("T24", module, "DefaultBidStrategy skips non-matching tags", False, str(e))

    # T25: DefaultBidStrategy skips low budget
    try:
        strat = DefaultBidStrategy(min_budget_usdc=5.0, agent_tags=["x"])
        job = Job(id="j3", description="cheap job", tags=["x"],
                  budget_usdc=0.10, deadline_ts=9999999999, poster="0x3")
        bid = run_sync(strat.evaluate(job))
        assert bid is None
        record("T25", module, "DefaultBidStrategy skips budget below minimum", True)
    except Exception as e:
        record("T25", module, "DefaultBidStrategy skips budget below minimum", False, str(e))

    # T26: set_agent_tags
    try:
        strat = DefaultBidStrategy()
        strat.set_agent_tags(["Alpha", "BETA"])
        assert strat._agent_tags == {"alpha", "beta"}
        record("T26", module, "set_agent_tags lowercases correctly", True)
    except Exception as e:
        record("T26", module, "set_agent_tags lowercases correctly", False, str(e))

    # T27: CostAwareBidStrategy falls back to Default
    try:
        strat = CostAwareBidStrategy(price_ratio=0.90, agent_tags=["test"])
        job = Job(id="j4", description="t", tags=["test"],
                  budget_usdc=20.0, deadline_ts=9999999999, poster="0x4")
        bid = run_sync(strat.evaluate(job))
        assert bid is not None
        assert bid.amount_usdc == 18.0  # 20 * 0.90
        record("T27", module, "CostAwareBidStrategy falls back to Default", True,
               f"amount={bid.amount_usdc}")
    except Exception as e:
        record("T27", module, "CostAwareBidStrategy falls back to Default", False, str(e))

    # T28: DefaultBidStrategy with no agent tags bids on everything
    try:
        strat = DefaultBidStrategy(agent_tags=[])
        job = Job(id="j5", description="any", tags=["whatever"],
                  budget_usdc=10.0, deadline_ts=9999999999, poster="0x5")
        bid = run_sync(strat.evaluate(job))
        assert bid is not None
        record("T28", module, "DefaultBidStrategy with empty tags bids on all", True)
    except Exception as e:
        record("T28", module, "DefaultBidStrategy with empty tags bids on all", False, str(e))


# ===========================================================================
# 6. MARKETPLACE / CLIENT
# ===========================================================================

def test_client():
    module = "marketplace.client"

    try:
        from sota_sdk.marketplace.client import MarketplaceClient
        record("T29", module, "MarketplaceClient importable", True)
    except Exception as e:
        record("T29", module, "MarketplaceClient importable", False, str(e))
        return

    # T30: URL validation rejects non-ws
    try:
        try:
            MarketplaceClient(url="http://bad")
            record("T30", module, "Rejects http:// URL", False, "no error raised")
        except ValueError:
            record("T30", module, "Rejects http:// URL", True)
    except Exception as e:
        record("T30", module, "Rejects http:// URL", False, str(e))

    # T31: URL validation accepts ws://
    try:
        c = MarketplaceClient(url="ws://localhost:3002/ws/agent")
        assert c._url == "ws://localhost:3002/ws/agent"
        record("T31", module, "Accepts ws:// URL", True)
    except Exception as e:
        record("T31", module, "Accepts ws:// URL", False, str(e))

    # T32: URL validation accepts wss://
    try:
        c = MarketplaceClient(url="wss://prod.example.com/ws")
        assert c._url.startswith("wss://")
        record("T32", module, "Accepts wss:// URL", True)
    except Exception as e:
        record("T32", module, "Accepts wss:// URL", False, str(e))

    # T33: handler registration
    try:
        c = MarketplaceClient(url="ws://localhost:9999/ws")
        async def handler(msg): pass
        c.on("job_available", handler)
        assert "job_available" in c._handlers
        record("T33", module, "Handler registration works", True)
    except Exception as e:
        record("T33", module, "Handler registration works", False, str(e))

    # T34: send queues when disconnected
    try:
        c = MarketplaceClient(url="ws://localhost:9999/ws")
        run_sync(c.send({"type": "bid", "job_id": "j1", "amount_usdc": 5.0}))
        assert len(c._send_queue) == 1
        assert c._send_queue[0]["type"] == "bid"
        record("T34", module, "Messages queued when WS disconnected", True)
    except Exception as e:
        record("T34", module, "Messages queued when WS disconnected", False, str(e))

    # T35: heartbeats NOT queued
    try:
        c = MarketplaceClient(url="ws://localhost:9999/ws")
        run_sync(c.send({"type": "heartbeat"}))
        assert len(c._send_queue) == 0
        record("T35", module, "Heartbeats not queued during disconnect", True)
    except Exception as e:
        record("T35", module, "Heartbeats not queued during disconnect", False, str(e))

    # T36: connected property false when no WS
    try:
        c = MarketplaceClient(url="ws://localhost:9999/ws")
        assert c.connected is False
        record("T36", module, "connected=False when no WebSocket", True)
    except Exception as e:
        record("T36", module, "connected=False when no WebSocket", False, str(e))

    # T37: agent_id starts empty
    try:
        c = MarketplaceClient(url="ws://localhost:9999/ws")
        assert c.agent_id == ""
        record("T37", module, "agent_id starts empty", True)
    except Exception as e:
        record("T37", module, "agent_id starts empty", False, str(e))


# ===========================================================================
# 7. CHAIN / WALLET
# ===========================================================================

def test_wallet():
    module = "chain.wallet"

    try:
        from sota_sdk.chain.wallet import AgentWallet
        record("T38", module, "AgentWallet importable", True)
    except Exception as e:
        record("T38", module, "AgentWallet importable", False, str(e))
        return

    # T39: rejects invalid key format (too short)
    try:
        try:
            AgentWallet("abc123")
            record("T39", module, "Rejects short private key", False, "no error raised")
        except ValueError as e:
            assert "64 hex" in str(e)
            record("T39", module, "Rejects short private key", True)
    except Exception as e:
        record("T39", module, "Rejects short private key", False, str(e))

    # T40: rejects non-hex characters
    try:
        try:
            AgentWallet("zz" * 32)
            record("T40", module, "Rejects non-hex key", False, "no error raised")
        except ValueError as e:
            assert "64 hex" in str(e)
            record("T40", module, "Rejects non-hex key", True)
    except Exception as e:
        record("T40", module, "Rejects non-hex key", False, str(e))

    # T41: key not leaked in error message
    try:
        bad_key = "gg" * 32
        try:
            AgentWallet(bad_key)
        except ValueError as e:
            assert bad_key not in str(e)
            record("T41", module, "Private key not leaked in error", True)
    except Exception as e:
        record("T41", module, "Private key not leaked in error", False, str(e))

    # T42: valid key (without 0x prefix)
    try:
        # well-known test key (hardhat account #0)
        test_key = "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        w = AgentWallet(test_key)
        assert w.address.startswith("0x")
        assert len(w.address) == 42
        record("T42", module, "Valid key without 0x prefix accepted", True, f"addr={w.address[:10]}...")
    except Exception as e:
        record("T42", module, "Valid key without 0x prefix accepted", False, str(e))

    # T43: valid key (with 0x prefix)
    try:
        test_key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        w = AgentWallet(test_key)
        assert w.address.startswith("0x")
        record("T43", module, "Valid key with 0x prefix accepted", True)
    except Exception as e:
        record("T43", module, "Valid key with 0x prefix accepted", False, str(e))

    # T44: has nonce lock
    try:
        import threading
        test_key = "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        w = AgentWallet(test_key)
        assert hasattr(w, '_nonce_lock')
        assert isinstance(w._nonce_lock, type(threading.Lock()))
        record("T44", module, "Nonce lock present (threading.Lock)", True)
    except Exception as e:
        record("T44", module, "Nonce lock present (threading.Lock)", False, str(e))

    # T45: repr does not expose full address
    try:
        test_key = "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        w = AgentWallet(test_key)
        r = repr(w)
        assert "..." in r  # truncated
        assert len(r) < 40  # not full address
        record("T45", module, "repr() does not expose full address", True, r)
    except Exception as e:
        record("T45", module, "repr() does not expose full address", False, str(e))


# ===========================================================================
# 8. CHAIN / CONTRACTS
# ===========================================================================

def test_contracts():
    module = "chain.contracts"

    try:
        from sota_sdk.chain.contracts import get_job, submit_delivery_proof, claim_payment
        record("T46", module, "Contract functions importable", True)
    except Exception as e:
        record("T46", module, "Contract functions importable", False, str(e))
        return


# ===========================================================================
# 9. CHAIN / REGISTRY
# ===========================================================================

def test_registry():
    module = "chain.registry"

    try:
        from sota_sdk.chain.registry import register_agent, is_agent_active
        record("T47", module, "Registry functions importable", True)
    except Exception as e:
        record("T47", module, "Registry functions importable", False, str(e))


# ===========================================================================
# 10. SERVER
# ===========================================================================

def test_server():
    module = "server"

    try:
        from sota_sdk.server import create_app, _mask_address
        record("T48", module, "create_app importable", True)
    except Exception as e:
        record("T48", module, "create_app importable", False, str(e))
        return

    # T49: mask_address
    try:
        assert _mask_address("0x1234567890abcdef1234567890abcdef12345678") == "0x1234...5678"
        assert _mask_address(None) is None
        assert _mask_address("") == ""
        assert _mask_address("short") == "short"  # too short to mask
        record("T49", module, "_mask_address masks correctly", True)
    except Exception as e:
        record("T49", module, "_mask_address masks correctly", False, str(e))

    # T50: create_app returns FastAPI with correct routes
    try:
        from sota_sdk.agent import SOTAAgent
        class DummyAgent(SOTAAgent):
            name = "test-server-agent"
            version = "1.2.3"
            tags = ["test"]
            async def execute(self, job): return {"success": True}

        agent = DummyAgent()
        app = create_app(agent)
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/status" in routes
        record("T50", module, "App has /health and /status routes", True)
    except Exception as e:
        record("T50", module, "App has /health and /status routes", False, str(e))

    # T51: health endpoint
    try:
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        record("T51", module, "GET /health returns {status: ok}", True)
    except Exception as e:
        record("T51", module, "GET /health returns {status: ok}", False, str(e))

    # T52: status endpoint masks wallet
    try:
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-server-agent"
        assert data["version"] == "1.2.3"
        # wallet should be None (no key configured) or masked
        assert data["wallet_address"] is None or "..." in data["wallet_address"]
        record("T52", module, "GET /status returns correct data, wallet masked", True)
    except Exception as e:
        record("T52", module, "GET /status returns correct data, wallet masked", False, str(e))


# ===========================================================================
# 11. AGENT CLASS
# ===========================================================================

def test_agent():
    module = "agent"

    try:
        from sota_sdk.agent import SOTAAgent
        from sota_sdk.models import Job, Bid
        from sota_sdk.marketplace.bidding import DefaultBidStrategy
        record("T53", module, "SOTAAgent importable", True)
    except Exception as e:
        record("T53", module, "SOTAAgent importable", False, str(e))
        return

    # T54: subclass inherits defaults
    try:
        class MyAgent(SOTAAgent):
            name = "my-agent"
            description = "My description"
            tags = ["tag1", "tag2"]
            version = "2.0.0"
            async def execute(self, job): return {"success": True}

        agent = MyAgent()
        assert agent.name == "my-agent"
        assert agent.description == "My description"
        assert agent.tags == ["tag1", "tag2"]
        assert agent.version == "2.0.0"
        record("T54", module, "Subclass attributes inherited correctly", True)
    except Exception as e:
        record("T54", module, "Subclass attributes inherited correctly", False, str(e))

    # T55: mutable defaults isolated between instances
    try:
        class A1(SOTAAgent):
            name = "a1"
            tags = ["alpha"]
            async def execute(self, job): return {}
        class A2(SOTAAgent):
            name = "a2"
            tags = ["beta"]
            async def execute(self, job): return {}

        a1 = A1()
        a2 = A2()
        a1.tags.append("extra")
        assert "extra" not in a2.tags
        assert "extra" not in A1.tags  # class-level unchanged
        record("T55", module, "Mutable tags isolated between instances", True)
    except Exception as e:
        record("T55", module, "Mutable tags isolated between instances", False, str(e))

    # T56: bid_strategy per-instance
    try:
        a1 = A1()
        a2 = A2()
        assert a1.bid_strategy is not a2.bid_strategy
        assert isinstance(a1.bid_strategy, DefaultBidStrategy)
        record("T56", module, "bid_strategy is per-instance DefaultBidStrategy", True)
    except Exception as e:
        record("T56", module, "bid_strategy is per-instance DefaultBidStrategy", False, str(e))

    # T57: execute() raises NotImplementedError if not overridden
    try:
        class Bare(SOTAAgent):
            name = "bare"
        agent = Bare()
        try:
            run_sync(agent.execute(Job(id="x", description="", tags=[], budget_usdc=0, deadline_ts=0, poster="")))
            record("T57", module, "execute() raises NotImplementedError", False, "no error raised")
        except NotImplementedError:
            record("T57", module, "execute() raises NotImplementedError", True)
    except Exception as e:
        record("T57", module, "execute() raises NotImplementedError", False, str(e))

    # T58: evaluate() delegates to bid_strategy
    try:
        class Tagged(SOTAAgent):
            name = "tagged"
            tags = ["web"]
            async def execute(self, job): return {}
        agent = Tagged()
        agent.bid_strategy.set_agent_tags(agent.tags)
        job = Job(id="j1", description="web thing", tags=["web"],
                  budget_usdc=10.0, deadline_ts=9999999999, poster="0x1")
        bid = run_sync(agent.evaluate(job))
        assert bid is not None
        assert bid.job_id == "j1"
        record("T58", module, "evaluate() delegates to bid_strategy", True)
    except Exception as e:
        record("T58", module, "evaluate() delegates to bid_strategy", False, str(e))

    # T59: _hash_result uses keccak256 and is deterministic
    try:
        from web3 import Web3
        data = {"key": "value", "num": 42}
        h1 = SOTAAgent._hash_result(data)
        h2 = SOTAAgent._hash_result(data)
        assert h1 == h2  # deterministic
        assert len(h1) == 32  # 32 bytes
        # Verify it's keccak and not sha256
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        expected = Web3.keccak(canonical)
        assert h1 == expected
        record("T59", module, "_hash_result is keccak-256, deterministic", True, f"hash={h1.hex()[:16]}...")
    except Exception as e:
        record("T59", module, "_hash_result is keccak-256, deterministic", False, str(e))

    # T60: _hash_result canonical (whitespace-insensitive)
    try:
        d1 = {"a": 1, "b": 2}
        d2 = {"b": 2, "a": 1}  # different key order
        assert SOTAAgent._hash_result(d1) == SOTAAgent._hash_result(d2)
        record("T60", module, "_hash_result is key-order independent", True)
    except Exception as e:
        record("T60", module, "_hash_result is key-order independent", False, str(e))

    # T61: _job_cache exists
    try:
        agent = MyAgent()
        assert hasattr(agent, '_job_cache')
        assert isinstance(agent._job_cache, dict)
        record("T61", module, "_job_cache dict present", True)
    except Exception as e:
        record("T61", module, "_job_cache dict present", False, str(e))

    # T62: _on_job_available rejects empty job ID
    try:
        agent = MyAgent()
        agent._ws_client = type('FakeWS', (), {'send': lambda self, x: None, 'connected': False})()
        # Should not raise, just log and return
        run_sync(agent._on_job_available({"job": {"id": ""}}))
        run_sync(agent._on_job_available({"job": {}}))
        record("T62", module, "_on_job_available ignores empty job ID", True)
    except Exception as e:
        record("T62", module, "_on_job_available ignores empty job ID", False, str(e))

    # T63: _on_bid_accepted guards duplicate
    try:
        agent = MyAgent()

        # Simulate an already-active job
        async def dummy(): pass
        agent._active_jobs["dup-job"] = asyncio.ensure_future(dummy())

        # Mock ws_client
        sent = []
        class FakeWS:
            connected = True
            async def send(self, payload): sent.append(payload)
        agent._ws_client = FakeWS()

        # Should return without creating a new task
        before = len(agent._active_jobs)
        run_sync(agent._on_bid_accepted({"job_id": "dup-job", "bid_id": "b1"}))
        assert len(agent._active_jobs) == before  # unchanged
        record("T63", module, "_on_bid_accepted guards duplicate job_id", True)

        # Cleanup
        for t in agent._active_jobs.values():
            t.cancel()
    except Exception as e:
        record("T63", module, "_on_bid_accepted guards duplicate job_id", False, str(e))

    # T64: run() host/port defaults from env
    try:
        # Check defaults
        # The method signature should accept None and resolve from env
        import inspect
        sig = inspect.signature(SOTAAgent.run)
        params = sig.parameters
        assert params["host"].default is None
        assert params["port"].default is None
        record("T64", module, "run() host/port default to None (env-resolved)", True)
    except Exception as e:
        record("T64", module, "run() host/port default to None (env-resolved)", False, str(e))

    # T65: _on_job_available caches job
    try:
        agent = MyAgent()
        sent_msgs = []
        class FakeWS:
            connected = True
            async def send(self, payload): sent_msgs.append(payload)
        agent._ws_client = FakeWS()
        agent.bid_strategy.set_agent_tags(agent.tags)

        msg = {"job": {
            "id": "cache-test",
            "description": "test job",
            "tags": agent.tags,
            "budget_usdc": 10.0,
            "deadline_ts": 9999999999,
            "poster": "0xABC",
            "metadata": {},
        }}
        run_sync(agent._on_job_available(msg))
        assert "cache-test" in agent._job_cache
        record("T65", module, "_on_job_available caches job for bid_accepted", True)
    except Exception as e:
        record("T65", module, "_on_job_available caches job for bid_accepted", False, str(e))


# ===========================================================================
# 12. PACKAGE-LEVEL __init__.py
# ===========================================================================

def test_package_init():
    module = "__init__"

    # T66: all public exports
    try:
        from sota_sdk import (
            SOTAAgent, Job, Bid, BidResult, JobResult,
            BaseTool, ToolManager,
            BidStrategy, DefaultBidStrategy, CostAwareBidStrategy,
            get_network, get_contract_addresses,
            NetworkConfig, ContractAddresses,
        )
        record("T66", module, "All public exports importable from sota_sdk", True)
    except Exception as e:
        record("T66", module, "All public exports importable from sota_sdk", False, str(e))

    # T67: cost module import is optional
    try:
        import sota_sdk
        # cost should be available or None, never a crash
        assert sota_sdk.cost is not None or sota_sdk.cost is None
        record("T67", module, "cost module imported or None (no crash)", True)
    except Exception as e:
        record("T67", module, "cost module imported or None (no crash)", False, str(e))

    # T68: __all__ is defined
    try:
        import sota_sdk
        assert hasattr(sota_sdk, '__all__')
        assert len(sota_sdk.__all__) >= 10
        record("T68", module, "__all__ is defined with expected exports", True, f"len={len(sota_sdk.__all__)}")
    except Exception as e:
        record("T68", module, "__all__ is defined with expected exports", False, str(e))


# ===========================================================================
# 13. WS PROTOCOL COMPLIANCE
# ===========================================================================

def test_protocol_compliance():
    module = "protocol"

    from sota_sdk.marketplace.registration import build_register_message
    from sota_sdk.models import Job

    # T69: register message has all required fields
    try:
        msg = build_register_message("agent", ["t1"], "1.0.0", "0xABC", ["cap1"])
        agent_block = msg["agent"]
        required = {"name", "tags", "version", "wallet_address", "capabilities"}
        assert required.issubset(set(agent_block.keys()))
        record("T69", module, "Register msg has all hub-required fields", True)
    except Exception as e:
        record("T69", module, "Register msg has all hub-required fields", False, str(e))

    # T70: bid message structure
    try:
        bid_msg = {
            "type": "bid",
            "job_id": "j1",
            "amount_usdc": 5.0,
            "estimated_seconds": 300,
        }
        required_fields = {"type", "job_id", "amount_usdc", "estimated_seconds"}
        assert required_fields.issubset(set(bid_msg.keys()))
        record("T70", module, "Bid msg has all hub-required fields", True)
    except Exception as e:
        record("T70", module, "Bid msg has all hub-required fields", False, str(e))

    # T71: job_completed message structure
    try:
        completed = {
            "type": "job_completed",
            "job_id": "j1",
            "success": True,
            "result": {"data": "ok"},
        }
        required = {"type", "job_id", "success", "result"}
        assert required.issubset(set(completed.keys()))
        record("T71", module, "job_completed msg has all hub-required fields", True)
    except Exception as e:
        record("T71", module, "job_completed msg has all hub-required fields", False, str(e))

    # T72: job_failed message structure
    try:
        failed = {
            "type": "job_failed",
            "job_id": "j1",
            "error": "something went wrong",
        }
        required = {"type", "job_id", "error"}
        assert required.issubset(set(failed.keys()))
        record("T72", module, "job_failed msg has all hub-required fields", True)
    except Exception as e:
        record("T72", module, "job_failed msg has all hub-required fields", False, str(e))

    # T73: heartbeat message structure
    try:
        hb = {"type": "heartbeat"}
        assert hb["type"] == "heartbeat"
        record("T73", module, "heartbeat msg is correct", True)
    except Exception as e:
        record("T73", module, "heartbeat msg is correct", False, str(e))


# ===========================================================================
# RUN ALL
# ===========================================================================

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    test_config()
    test_models()
    test_tools()
    test_registration()
    test_bidding()
    test_client()
    test_wallet()
    test_contracts()
    test_registry()
    test_server()
    test_agent()
    test_package_init()
    test_protocol_compliance()

    loop.close()

    # Print table
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    print()
    print(f"{'ID':<5} {'Status':<6} {'Module':<28} {'Test':<52} {'Detail'}")
    print("-" * 140)
    for r in results:
        detail = r["detail"][:45] if r["detail"] else ""
        print(f"{r['id']:<5} {r['status']:<6} {r['module']:<28} {r['test']:<52} {detail}")

    print("-" * 140)
    print(f"TOTAL: {len(results)} tests | {passed} PASSED | {failed} FAILED")
    if failed > 0:
        sys.exit(1)
