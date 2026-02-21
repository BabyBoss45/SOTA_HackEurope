"""
SOTA Agent Builder — Standalone Web UI

Served by `sota ui`. No Node/npm needed — just FastAPI + static files.
Lets developers visually configure and generate agent projects.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Reuse templates from CLI so there's a single source of truth
from ..cli import (
    AGENT_TEMPLATE,
    DOCKERFILE_TEMPLATE,
    DOCKERIGNORE_TEMPLATE,
    ENV_TEMPLATE,
    README_TEMPLATE,
    REQUIREMENTS_TEMPLATE,
    _to_class_name,
)

STATIC_DIR = Path(__file__).parent / "static"


class AgentConfig(BaseModel):
    name: str = "my-agent"
    description: str = ""
    tags: list[str] = ["my_capability"]
    version: str = "1.0.0"
    private_key: str = ""
    marketplace_url: str = "ws://localhost:3002/ws/agent"
    chain: str = "base-sepolia"
    price_ratio: float = 0.80
    min_budget: float = 0.50


class CheckRequest(BaseModel):
    name: str = ""
    tags: list[str] = []
    marketplace_url: str = ""
    private_key: str = ""


def _generate_files(config: AgentConfig) -> dict[str, str]:
    """Generate all agent project files from config."""
    tags_str = ", ".join(f'"{t}"' for t in config.tags)
    class_name = _to_class_name(config.name)

    # Build .env with user values filled in
    env_lines = []
    if config.private_key:
        env_lines.append("SOTA_AGENT_PRIVATE_KEY=  # PASTE YOUR KEY HERE (never commit this file)")
    else:
        env_lines.append("SOTA_AGENT_PRIVATE_KEY=           # 64 hex chars")
    env_lines.append(f"SOTA_MARKETPLACE_URL={config.marketplace_url}")

    chain_map = {"base-sepolia": "84532", "base-mainnet": "8453", "hardhat": "31337"}
    env_lines.append(f"CHAIN_ID={chain_map.get(config.chain, '84532')}")

    # Build agent.py with bid strategy if non-default
    agent_code = AGENT_TEMPLATE.format(
        name=config.name, class_name=class_name, tags=tags_str,
    )

    # If custom bid strategy params, inject them
    if config.price_ratio != 0.80 or config.min_budget != 0.50:
        bid_import = "from sota_sdk import SOTAAgent, Job, DefaultBidStrategy"
        bid_attr = (
            f"    bid_strategy = DefaultBidStrategy("
            f"price_ratio={config.price_ratio}, min_budget_usdc={config.min_budget})"
        )
        agent_code = agent_code.replace(
            "from sota_sdk import SOTAAgent, Job",
            bid_import,
        )
        agent_code = agent_code.replace(
            f'    tags = [{tags_str}]',
            f'    tags = [{tags_str}]\n{bid_attr}',
        )

    # Add description if provided
    if config.description:
        agent_code = agent_code.replace(
            '    description = "TODO: describe what this agent does"',
            f'    description = "{config.description}"',
        )

    return {
        "agent.py": agent_code,
        ".env": "\n".join(env_lines) + "\n",
        ".env.example": ENV_TEMPLATE,
        "requirements.txt": REQUIREMENTS_TEMPLATE,
        "Dockerfile": DOCKERFILE_TEMPLATE,
        ".dockerignore": DOCKERIGNORE_TEMPLATE,
        "README.md": README_TEMPLATE.format(name=config.name),
    }


def create_ui_app() -> FastAPI:
    """Build the Agent Builder FastAPI app."""
    app = FastAPI(title="SOTA Agent Builder")

    # Serve static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = STATIC_DIR / "index.html"
        return HTMLResponse(html_path.read_text())

    @app.post("/api/generate")
    async def generate(config: AgentConfig):
        """Generate agent files and return as JSON (private key redacted)."""
        files = _generate_files(config)
        # Never echo the private key back in API responses
        response_files = {k: v for k, v in files.items()}
        if config.private_key and ".env" in response_files:
            response_files[".env"] = response_files[".env"].replace(
                config.private_key, "***REDACTED***"
            )
        return {"files": response_files}

    @app.post("/api/download")
    async def download(config: AgentConfig):
        """Generate agent files and return as ZIP."""
        files = _generate_files(config)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in files.items():
                zf.writestr(f"{config.name}/{filename}", content)
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{config.name}.zip"'
            },
        )

    @app.post("/api/check")
    async def check(req: CheckRequest):
        """Run preflight validation on the provided config."""
        errors = []
        warnings = []

        if not req.name or req.name == "unnamed-agent":
            errors.append("Agent name is required.")
        if not req.tags:
            errors.append("At least one tag is required.")
        if req.marketplace_url and not req.marketplace_url.startswith(("ws://", "wss://")):
            errors.append("Marketplace URL must start with ws:// or wss://")
        if req.private_key:
            hex_re = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")
            if not hex_re.match(req.private_key):
                errors.append("Private key must be 64 hex characters (optional 0x prefix).")
        else:
            warnings.append("No private key — agent will run off-chain only.")

        if req.marketplace_url and req.marketplace_url.startswith("ws://") and "localhost" not in req.marketplace_url and "127.0.0.1" not in req.marketplace_url:
            warnings.append("Using unencrypted ws://. Use wss:// in production.")

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    @app.get("/api/templates")
    async def templates():
        """List available example templates."""
        return {
            "templates": [
                {"id": "echo", "name": "Echo Agent", "description": "Simplest agent — echoes job descriptions"},
                {"id": "llm", "name": "LLM Agent", "description": "Uses Anthropic Claude for question answering"},
                {"id": "tool", "name": "Tool Agent", "description": "Custom tools with BaseTool + ToolManager"},
                {"id": "bid", "name": "Custom Bid Agent", "description": "Custom BidStrategy implementation"},
            ]
        }

    @app.get("/api/networks")
    async def networks():
        """Return supported chains and their config."""
        return {
            "networks": [
                {"id": "base-sepolia", "name": "Base Sepolia (Testnet)", "chain_id": 84532, "rpc": "https://sepolia.base.org"},
                {"id": "base-mainnet", "name": "Base Mainnet", "chain_id": 8453, "rpc": "https://mainnet.base.org"},
                {"id": "hardhat", "name": "Hardhat Local", "chain_id": 31337, "rpc": "http://127.0.0.1:8545"},
            ]
        }

    return app
