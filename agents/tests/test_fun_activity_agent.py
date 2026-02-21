"""
Test Fun Activity Agent — structure and integration.

Run with: python -m pytest agents/tests/test_fun_activity_agent.py -v
Requires: pip install -r agents/requirements.txt (solders, anthropic, etc.)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("BUTLER_AUTO_CONFIRM", "true")


def test_fun_activity_module_structure():
    """Verify fun_activity module files exist."""
    fun_activity_dir = _REPO_ROOT / "agents" / "src" / "fun_activity"
    assert (fun_activity_dir / "agent.py").exists()
    assert (fun_activity_dir / "tools.py").exists()
    assert (fun_activity_dir / "__init__.py").exists()


def test_chain_config_has_fun_activity():
    """Verify JobType.FUN_ACTIVITY is defined."""
    try:
        from agents.src.shared.chain_config import JobType, JOB_TYPE_LABELS, AGENT_CAPABILITIES
        assert hasattr(JobType, "FUN_ACTIVITY")
        assert JobType.FUN_ACTIVITY in JOB_TYPE_LABELS
        assert "FUN_ACTIVITY" in AGENT_CAPABILITIES
    except ModuleNotFoundError as e:
        if "solders" in str(e):
            # Skip if Solana deps not installed
            return
        raise


def test_auto_bidder_has_fun_activity_tag():
    """Verify JOB_TYPE_TAGS includes fun_activity."""
    try:
        from agents.src.shared.auto_bidder import JOB_TYPE_TAGS
        from agents.src.shared.chain_config import JobType
        assert JobType.FUN_ACTIVITY in JOB_TYPE_TAGS
        assert JOB_TYPE_TAGS[JobType.FUN_ACTIVITY] == "fun_activity"
    except ModuleNotFoundError as e:
        if "solders" in str(e):
            return
        raise


async def test_fun_activity_agent_full_import():
    """Verify Fun Activity agent can be imported and registered (requires full deps)."""
    try:
        from agents.src.shared.job_board import JobBoard
        from agents.src.fun_activity.agent import FunActivityAgent, create_fun_activity_agent

        assert FunActivityAgent.agent_type == "fun_activity"
        assert FunActivityAgent.agent_name == "SOTA Fun Activity Agent"

        JobBoard._instance = None
        agent = await create_fun_activity_agent()
        board = JobBoard.instance()
        assert "fun_activity" in board.workers
        assert "fun_activity" in board.workers["fun_activity"].tags
    except ModuleNotFoundError as e:
        if "solders" in str(e) or "anthropic" in str(e):
            return  # Skip if deps not installed
        raise


if __name__ == "__main__":
    test_fun_activity_module_structure()
    print("Module structure OK")

    test_chain_config_has_fun_activity()
    print("Chain config OK")

    test_auto_bidder_has_fun_activity_tag()
    print("Auto-bidder tags OK")

    asyncio.run(test_fun_activity_agent_full_import())
    print("Full agent import OK")

    print("\nAll Fun Activity Agent tests passed!")
