"""SOTA Agents - Main Entry Point

Run individual agents or the full agent system.
"""

import os
import sys
import asyncio
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_butler_api():
    """Run the Butler API"""
    import uvicorn
    logger.info("🚀 Starting SOTA Butler API on port 3001...")
    uvicorn.run(
        "agents.butler_api:app",
        host="0.0.0.0",
        port=int(os.environ.get("BUTLER_API_PORT", 3001)),
        reload=False,
    )


async def run_manager():
    """Run the Manager Agent server"""
    from agents.src.manager.server import run_server
    logger.info("🚀 Starting Manager Agent on port 3002...")
    run_server()


async def run_caller():
    """Run the Caller Agent server"""
    from agents.src.caller.server import run_server
    logger.info("🚀 Starting Caller Agent on port 3003...")
    run_server()


def run_x402():
    """Run the x402 Paid Data API"""
    import uvicorn
    logger.info("🚀 Starting SOTA x402 Data API on port 3004...")
    uvicorn.run(
        "agents.src.x402.server:app",
        host="0.0.0.0",
        port=int(os.environ.get("X402_PORT", 3004)),
        reload=False,
    )


def main():
    parser = argparse.ArgumentParser(
        description="SOTA Agent Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m agents butler     # Run Butler API (default)
  python -m agents manager    # Run Manager Agent
  python -m agents caller     # Run Caller Agent
  python -m agents x402       # Run x402 Paid Data API
  python -m agents all        # Print multi-process instructions
        """
    )

    parser.add_argument(
        "agent",
        choices=["butler", "manager", "caller", "x402", "all"],
        help="Which agent to run"
    )

    parser.add_argument(
        "--port",
        type=int,
        help="Override default port for the agent"
    )

    args = parser.parse_args()

    # Set port override
    if args.port:
        if args.agent == "butler":
            os.environ["BUTLER_API_PORT"] = str(args.port)
        elif args.agent == "manager":
            os.environ["MANAGER_PORT"] = str(args.port)
        elif args.agent == "caller":
            os.environ["CALLER_PORT"] = str(args.port)
        elif args.agent == "x402":
            os.environ["X402_PORT"] = str(args.port)

    # Run selected agent
    if args.agent == "butler":
        run_butler_api()
    elif args.agent == "manager":
        asyncio.run(run_manager())
    elif args.agent == "caller":
        asyncio.run(run_caller())
    elif args.agent == "x402":
        run_x402()
    elif args.agent == "all":
        print("""
To run all agents, use separate terminal windows:

Terminal 1:  python -m agents butler   # Butler API (port 3001)
Terminal 2:  python -m agents manager  # Manager    (port 3002)
Terminal 3:  python -m agents caller   # Caller     (port 3003)
Terminal 4:  python -m agents x402     # x402 API   (port 3004)

Or use Docker Compose:  docker compose up
        """)
        sys.exit(0)


if __name__ == "__main__":
    main()
