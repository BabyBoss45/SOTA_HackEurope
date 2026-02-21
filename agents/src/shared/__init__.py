"""
SOTA Agents — Shared Utilities

Provides common functionality used across all agents:
- chain_config: Network settings (Base Sepolia, Base Mainnet)
- chain_contracts: Smart contract interaction (OrderBook, Escrow, etc.)
- a2a: Agent-to-Agent communication protocol
- config: Re-exports from chain_config (backward compat)
- contracts: Re-exports from chain_contracts (backward compat)
- agent_runner: Anthropic-powered tool-calling agent loop
- tool_base: BaseTool + ToolManager for function-calling tools
- job_board: In-memory marketplace (JobBoard singleton)
"""

from .chain_config import *
from .chain_contracts import *
from .a2a import *

# Core agent infrastructure (Anthropic)
from .agent_runner import AgentRunner, LLMClient
from .tool_base import BaseTool, ToolManager
from .job_board import JobBoard, JobListing, Bid, BidResult, JobStatus
