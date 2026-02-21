"""
Pre-flight validation for SOTA SDK agents.

Runs automatically during SOTAAgent._boot() before wallet init.
Collects all errors and warnings in a single pass so developers
see every issue at once instead of fixing them one by one.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import SOTAAgent

logger = logging.getLogger(__name__)

_HEX64_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


@dataclass
class PreflightResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def merge(self, other: "PreflightResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def _check_agent_class(agent: "SOTAAgent") -> PreflightResult:
    """Validate the agent subclass definition."""
    r = PreflightResult()

    if agent.name == "unnamed-agent":
        r.errors.append(
            "Agent 'name' not set. Add:  name = \"my-agent\"  to your class."
        )

    if not agent.tags:
        r.errors.append(
            "Agent 'tags' is empty. Add:  tags = [\"your_capability\"]  "
            "so the hub can match jobs to your agent."
        )

    # Check execute() is overridden
    from .agent import SOTAAgent as _Base
    if type(agent).execute is _Base.execute:
        r.errors.append(
            "execute() not implemented. Override it to handle jobs."
        )

    if not agent.description:
        r.warnings.append(
            "Agent 'description' is empty. Consider adding a description "
            "so other users know what your agent does."
        )

    return r


def _check_environment() -> PreflightResult:
    """Validate environment variables and configuration."""
    r = PreflightResult()

    # Marketplace URL
    from .config import SOTA_MARKETPLACE_URL
    url = SOTA_MARKETPLACE_URL
    if not url:
        r.errors.append("SOTA_MARKETPLACE_URL is empty. Set it to ws://<hub-host>:3002/ws/agent")
    elif not url.startswith(("ws://", "wss://")):
        r.errors.append(
            f"SOTA_MARKETPLACE_URL must start with ws:// or wss://, got: {url}"
        )
    elif url.startswith("ws://") and "localhost" not in url and "127.0.0.1" not in url:
        r.warnings.append(
            "SOTA_MARKETPLACE_URL uses unencrypted ws://. Use wss:// in production."
        )

    # Private key format (if provided)
    from .config import SOTA_AGENT_PRIVATE_KEY
    key = SOTA_AGENT_PRIVATE_KEY
    if key:
        if not _HEX64_RE.match(key):
            r.errors.append(
                "SOTA_AGENT_PRIVATE_KEY is malformed. "
                "Must be 64 hex characters (optionally prefixed with 0x)."
            )
    else:
        r.warnings.append(
            "SOTA_AGENT_PRIVATE_KEY not set. Agent will run off-chain only "
            "(no delivery proofs, no payment claims)."
        )

    # Contract addresses
    from .config import get_contract_addresses
    contracts = get_contract_addresses()
    if not contracts.order_book:
        r.warnings.append(
            "Contract addresses not found. On-chain features (delivery proof, "
            "payment) will be unavailable. Set ORDERBOOK_ADDRESS env var or "
            "ensure contracts/deployments/ directory exists."
        )

    return r


def _check_rpc_connectivity() -> PreflightResult:
    """Quick check that the RPC endpoint responds (non-blocking, warning only)."""
    r = PreflightResult()
    try:
        from .config import get_network
        import urllib.request
        import urllib.error

        network = get_network()
        req = urllib.request.Request(
            network.rpc_url,
            data=b'{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                r.warnings.append(
                    f"RPC endpoint {network.rpc_url} returned HTTP {resp.status}. "
                    "On-chain features may not work."
                )
    except Exception as e:
        r.warnings.append(
            f"RPC endpoint unreachable: {e}. "
            "On-chain features may not work. Check RPC_URL."
        )
    return r


def run_preflight(agent: "SOTAAgent", check_rpc: bool = True) -> PreflightResult:
    """Run all preflight checks and return aggregated results."""
    result = PreflightResult()

    result.merge(_check_agent_class(agent))
    result.merge(_check_environment())

    if check_rpc:
        result.merge(_check_rpc_connectivity())

    return result
