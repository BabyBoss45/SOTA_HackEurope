"""
SOTA Agent SDK

Install, subclass SOTAAgent, implement execute(), call run(). That's it.

    from sota_sdk import SOTAAgent, Job

    class MyAgent(SOTAAgent):
        name = "my-agent"
        tags = ["data_analysis"]

        async def execute(self, job: Job) -> dict:
            return {"success": True, "answer": 42}

    if __name__ == "__main__":
        MyAgent.run()
"""

try:
    from . import cost
except ImportError:
    cost = None  # type: ignore[assignment]

from .agent import SOTAAgent
from .config import (
    get_network,
    get_cluster,
    get_contract_addresses,
    get_keypair,
    NetworkConfig,
    ClusterConfig,
    ContractAddresses,
    PROGRAM_ID,
    USDC_MINT,
)
from .models import Job, Bid, BidResult, JobResult
from .tools import BaseTool, ToolManager
from .marketplace.bidding import BidStrategy, DefaultBidStrategy, CostAwareBidStrategy
from .preflight import run_preflight, PreflightResult

__all__ = [
    # Core
    "SOTAAgent",
    # Models
    "Job",
    "Bid",
    "BidResult",
    "JobResult",
    # Tools
    "BaseTool",
    "ToolManager",
    # Bid strategies
    "BidStrategy",
    "DefaultBidStrategy",
    "CostAwareBidStrategy",
    # Config
    "get_network",
    "get_cluster",
    "get_contract_addresses",
    "get_keypair",
    "NetworkConfig",
    "ClusterConfig",
    "ContractAddresses",
    "PROGRAM_ID",
    "USDC_MINT",
    # Preflight validation
    "run_preflight",
    "PreflightResult",
    # Cost tracking (Paid.ai — Task 3)
    "cost",
]
