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


# ── Agent port env var mapping ───────────────────────────────
AGENT_PORT_ENVS = {
    "butler":             "BUTLER_API_PORT",
    "manager":            "MANAGER_PORT",
    "caller":             "CALLER_PORT",
    "x402":               "X402_PORT",
    "hackathon":          "HACKATHON_AGENT_PORT",
    "gift_suggestion":    "GIFT_AGENT_PORT",
    "restaurant_booker":  "RESTAURANT_AGENT_PORT",
    "refund_claim":       "REFUND_AGENT_PORT",
    "smart_shopper":      "SHOPPER_AGENT_PORT",
    "trip_planner":       "TRIP_AGENT_PORT",
}

ALL_AGENTS = list(AGENT_PORT_ENVS.keys()) + ["all"]


def run_butler_api():
    """Run the Butler API"""
    import uvicorn
    logger.info("Starting SOTA Butler API on port 3001...")
    uvicorn.run(
        "agents.butler_api:app",
        host="0.0.0.0",
        port=int(os.environ.get("BUTLER_API_PORT", 3001)),
        reload=False,
    )


async def run_manager():
    """Run the Manager Agent server"""
    from agents.src.manager.server import run_server
    logger.info("Starting Manager Agent on port 3002...")
    run_server()


async def run_caller():
    """Run the Caller Agent server"""
    from agents.src.caller.server import run_server
    logger.info("Starting Caller Agent on port 3003...")
    run_server()


def run_x402():
    """Run the x402 Paid Data API"""
    import uvicorn
    logger.info("Starting SOTA x402 Data API on port 3004...")
    uvicorn.run(
        "agents.src.x402.server:app",
        host="0.0.0.0",
        port=int(os.environ.get("X402_PORT", 3004)),
        reload=False,
    )


def run_hackathon():
    """Run the Hackathon Agent server"""
    from agents.src.hackathon.server import run_server
    logger.info("Starting Hackathon Agent on port 3005...")
    run_server()


def run_gift_suggestion():
    """Run the Gift Suggestion Agent server"""
    from agents.src.gift_suggestion.server import run_server
    logger.info("Starting Gift Suggestion Agent on port 3007...")
    run_server()


def run_restaurant_booker():
    """Run the Restaurant Booker Agent server"""
    from agents.src.restaurant_booker.server import run_server
    logger.info("Starting Restaurant Booker Agent on port 3008...")
    run_server()


def run_refund_claim():
    """Run the Refund Claim Agent server"""
    from agents.src.refund_claim.server import run_server
    logger.info("Starting Refund Claim Agent on port 3009...")
    run_server()


def run_smart_shopper():
    """Run the Smart Shopper Agent server"""
    from agents.src.smart_shopper.server import run_server
    logger.info("Starting Smart Shopper Agent on port 3010...")
    run_server()


def run_trip_planner():
    """Run the Trip Planner Agent server"""
    from agents.src.trip_planner.server import run_server
    logger.info("Starting Trip Planner Agent on port 3011...")
    run_server()


def main():
    parser = argparse.ArgumentParser(
        description="SOTA Agent Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m agents butler             # Butler API      (port 3001)
  python -m agents manager            # Manager         (port 3002)
  python -m agents caller             # Caller          (port 3003)
  python -m agents x402               # x402 API        (port 3004)
  python -m agents hackathon          # Hackathon       (port 3005)
  python -m agents gift_suggestion    # Gift Suggestion (port 3007)
  python -m agents restaurant_booker  # Restaurant      (port 3008)
  python -m agents refund_claim       # Refund Claim    (port 3009)
  python -m agents smart_shopper      # Smart Shopper   (port 3010)
  python -m agents trip_planner       # Trip Planner    (port 3011)
  python -m agents all                # Print multi-process instructions
        """
    )

    parser.add_argument(
        "agent",
        choices=ALL_AGENTS,
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
        env_key = AGENT_PORT_ENVS.get(args.agent)
        if env_key:
            os.environ[env_key] = str(args.port)

    # Run selected agent
    runners = {
        "butler":             run_butler_api,
        "manager":            lambda: asyncio.run(run_manager()),
        "caller":             lambda: asyncio.run(run_caller()),
        "x402":               run_x402,
        "hackathon":          run_hackathon,
        "gift_suggestion":    run_gift_suggestion,
        "restaurant_booker":  run_restaurant_booker,
        "refund_claim":       run_refund_claim,
        "smart_shopper":      run_smart_shopper,
        "trip_planner":       run_trip_planner,
    }

    if args.agent == "all":
        print("""
To run all agents, use separate terminal windows:

Terminal 1:   python -m agents butler             # Butler API      (port 3001)
Terminal 2:   python -m agents manager            # Manager         (port 3002)
Terminal 3:   python -m agents caller             # Caller          (port 3003)
Terminal 4:   python -m agents x402               # x402 API        (port 3004)
Terminal 5:   python -m agents hackathon          # Hackathon       (port 3005)
Terminal 6:   python -m agents gift_suggestion    # Gift Suggestion (port 3007)
Terminal 7:   python -m agents restaurant_booker  # Restaurant      (port 3008)
Terminal 8:   python -m agents refund_claim       # Refund Claim    (port 3009)
Terminal 9:   python -m agents smart_shopper      # Smart Shopper   (port 3010)
Terminal 10:  python -m agents trip_planner       # Trip Planner    (port 3011)

Or use Docker Compose:  docker compose up
        """)
        sys.exit(0)

    runners[args.agent]()


if __name__ == "__main__":
    main()
