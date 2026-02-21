"""
SOTA SDK CLI

Usage:
    sota init my-agent --tags web_scraping nlp    # Scaffold a new agent project
    sota check [agent.py]                          # Preflight validation (dry-run)
    sota run [agent.py] [--port 8000]              # Run an agent
    sota ui [--port 5173]                          # Launch the web UI
    sota docker                                    # Generate Dockerfile
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import os
import re
import sys
import textwrap
import webbrowser
from pathlib import Path
from typing import Optional, Type


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

AGENT_TEMPLATE = '''\
"""
{name} -- SOTA Marketplace Agent

Created with: sota init {name}
Run with:     sota run
"""
from sota_sdk import SOTAAgent, Job


class {class_name}(SOTAAgent):
    name = "{name}"
    description = "TODO: describe what this agent does"
    tags = [{tags}]

    def setup(self):
        """Called once at startup. Initialize API clients, load models, etc."""
        pass

    async def execute(self, job: Job) -> dict:
        """Execute a job and return results.

        Args:
            job: Contains job.description, job.params, job.budget_usdc, etc.

        Returns:
            Dict with at least {{"success": True/False}} plus any result data.
        """
        # TODO: implement your agent logic here
        return {{"success": True, "result": f"Processed: {{job.description}}"}}


if __name__ == "__main__":
    {class_name}.run()
'''

ENV_TEMPLATE = '''\
# === Required (for on-chain features) ===
SOTA_AGENT_PRIVATE_KEY=           # 64 hex chars (your agent wallet key)

# === Marketplace Hub ===
# SOTA_MARKETPLACE_URL=ws://localhost:3002/ws/agent

# === Blockchain ===
# CHAIN_ID=84532                  # Base Sepolia
# RPC_URL=https://sepolia.base.org

# === Optional ===
# SOTA_AGENT_HOST=127.0.0.1
# SOTA_AGENT_PORT=8000
'''

REQUIREMENTS_TEMPLATE = "sota-sdk>=0.3.0\n"

DOCKERFILE_TEMPLATE = '''\
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["python", "agent.py"]
'''

DOCKERIGNORE_TEMPLATE = '''\
__pycache__
*.pyc
.env
.git
.venv
.pytest_cache
'''

README_TEMPLATE = '''\
# {name}

SOTA Marketplace Agent created with `sota init`.

## Quick Start

```bash
# 1. Edit agent.py -- implement your execute() logic
# 2. Configure .env with your private key
cp .env.example .env

# 3. Run locally
sota run

# 4. Deploy with Docker
docker build -t {name} .
docker run --env-file .env -p 8000:8000 {name}
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SOTA_AGENT_PRIVATE_KEY` | For on-chain | 64-hex-char wallet key |
| `SOTA_MARKETPLACE_URL` | No | Hub WebSocket URL (default: ws://localhost:3002/ws/agent) |
| `CHAIN_ID` | No | 84532 (Base Sepolia, default) |
'''


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_class_name(name: str) -> str:
    """Convert 'my-cool-agent' to 'MyCoolAgent'."""
    parts = re.split(r"[-_ ]+", name)
    return "".join(p.capitalize() for p in parts) + "Agent"


def _discover_agent_class(file_path: str) -> Optional[Type]:
    """Import a Python file and find the SOTAAgent subclass."""
    path = Path(file_path).resolve()
    if not path.exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("_user_agent", str(path))
    if not spec or not spec.loader:
        print(f"Error: Cannot load module from: {path}")
        sys.exit(1)

    # Add parent to sys.path so relative imports work
    parent = str(path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from .agent import SOTAAgent

    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, SOTAAgent) and obj is not SOTAAgent:
            return obj

    print(f"Error: No SOTAAgent subclass found in {path}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold a new agent project."""
    name = args.name
    directory = Path(args.directory or name)

    if directory.exists() and any(directory.iterdir()):
        print(f"Error: Directory '{directory}' already exists and is not empty.")
        sys.exit(1)

    directory.mkdir(parents=True, exist_ok=True)

    tags_str = ", ".join(f'"{t}"' for t in args.tags) if args.tags else '"my_capability"'
    class_name = _to_class_name(name)

    files = {
        "agent.py": AGENT_TEMPLATE.format(
            name=name, class_name=class_name, tags=tags_str,
        ),
        ".env.example": ENV_TEMPLATE,
        "requirements.txt": REQUIREMENTS_TEMPLATE,
        "Dockerfile": DOCKERFILE_TEMPLATE,
        ".dockerignore": DOCKERIGNORE_TEMPLATE,
        "README.md": README_TEMPLATE.format(name=name),
    }

    for filename, content in files.items():
        (directory / filename).write_text(content)

    print(f"Agent project created in ./{directory}/")
    print()
    print("Next steps:")
    print(f"  cd {directory}")
    print("  # Edit agent.py -- implement your execute() logic")
    print("  cp .env.example .env   # Add your private key")
    print("  sota run               # Start your agent")


def cmd_check(args: argparse.Namespace) -> None:
    """Run preflight validation without starting the agent."""
    import asyncio

    agent_file = args.agent_file or _find_agent_file()

    cls = _discover_agent_class(agent_file)
    agent = cls()

    try:
        if asyncio.iscoroutinefunction(agent.setup):
            asyncio.run(agent.setup())
        else:
            agent.setup()
    except Exception as e:
        print(f"\n  Error in setup(): {e}")
        print("  Fix your setup() method and try again.")
        sys.exit(1)

    from .preflight import run_preflight

    result = run_preflight(agent, check_rpc=not args.skip_rpc)

    if result.warnings:
        print(f"\n  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    - {w}")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for e in result.errors:
            print(f"    - {e}")
        print(f"\n  FAILED -- {len(result.errors)} error(s)")
        sys.exit(1)
    else:
        print("\n  All checks passed!")


def cmd_run(args: argparse.Namespace) -> None:
    """Discover and run an agent from a Python file."""
    agent_file = args.agent_file or _find_agent_file()

    cls = _discover_agent_class(agent_file)
    cls.run(port=args.port, host=args.host)


def cmd_ui(args: argparse.Namespace) -> None:
    """Launch the standalone web UI."""
    port = args.port or 5173

    from .ui.app import create_ui_app

    import uvicorn

    url = f"http://127.0.0.1:{port}"
    print(f"SOTA Agent Builder starting at {url}")
    print("Press Ctrl+C to stop.\n")

    # Open browser after a short delay
    import threading
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        create_ui_app(),
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )


def cmd_docker(args: argparse.Namespace) -> None:
    """Generate a Dockerfile in the current directory."""
    dockerfile = Path("Dockerfile")
    if dockerfile.exists() and not args.force:
        print("Dockerfile already exists. Use --force to overwrite.")
        sys.exit(1)

    dockerfile.write_text(DOCKERFILE_TEMPLATE)
    Path(".dockerignore").write_text(DOCKERIGNORE_TEMPLATE)
    print("Generated: Dockerfile, .dockerignore")
    print()
    print("Build and run:")
    print("  docker build -t my-agent .")
    print("  docker run --env-file .env -p 8000:8000 my-agent")


def _find_agent_file() -> str:
    """Look for agent.py in the current directory."""
    for candidate in ["agent.py", "main.py"]:
        if Path(candidate).exists():
            return candidate
    print("Error: No agent.py found in current directory. Specify the file path:")
    print("  sota run my_agent.py")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sota",
        description="SOTA Agent SDK -- build and deploy marketplace agents",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help="Scaffold a new agent project")
    init_p.add_argument("name", help="Agent name (e.g., my-scraper)")
    init_p.add_argument("--tags", nargs="+", default=[], help="Capability tags")
    init_p.add_argument("--directory", "-d", help="Output directory (default: same as name)")

    # check
    check_p = sub.add_parser("check", help="Run preflight validation (dry-run)")
    check_p.add_argument("agent_file", nargs="?", help="Agent file (default: agent.py)")
    check_p.add_argument("--skip-rpc", action="store_true", help="Skip RPC connectivity check")

    # run
    run_p = sub.add_parser("run", help="Run an agent")
    run_p.add_argument("agent_file", nargs="?", help="Agent file (default: agent.py)")
    run_p.add_argument("--port", type=int, help="HTTP port override")
    run_p.add_argument("--host", help="Bind host override")

    # ui
    ui_p = sub.add_parser("ui", help="Launch the web-based Agent Builder")
    ui_p.add_argument("--port", type=int, default=5173, help="UI port (default: 5173)")

    # docker
    docker_p = sub.add_parser("docker", help="Generate Dockerfile for your agent")
    docker_p.add_argument("--force", action="store_true", help="Overwrite existing Dockerfile")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "init": cmd_init,
        "check": cmd_check,
        "run": cmd_run,
        "ui": cmd_ui,
        "docker": cmd_docker,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
