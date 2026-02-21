/**
 * Shared agent project template generators.
 *
 * Used by:
 *  - app/developers/deploy/page.tsx  (live preview)
 *  - app/api/agents/deploy/route.ts  (ZIP generation)
 *
 * Mirrors the Python templates in agents/sota_sdk/cli.py.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AgentTemplateConfig {
  name: string;
  description: string;
  tags: string[];
  capabilities: string[];
  priceRatio: number;
  minFeeUsdc: number;
  walletAddress: string;
  hubUrl: string;
  chain: string;
}

// ---------------------------------------------------------------------------
// Sanitisation — prevent injection into Python string literals
// ---------------------------------------------------------------------------

/** Escape a value so it is safe inside a Python double-quoted string. */
function pyEscape(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r');
}

/** Sanitise an agent name to filesystem-safe slug (a-z, 0-9, dash, underscore). */
export function sanitiseName(name: string): string {
  return name.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function toClassName(name: string): string {
  return (
    name
      .split(/[-_ ]+/)
      .filter(Boolean)
      .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
      .join('') + 'Agent'
  );
}

// ---------------------------------------------------------------------------
// Template generators
// ---------------------------------------------------------------------------

export function generateAgentPy(c: AgentTemplateConfig): string {
  const safeName = pyEscape(c.name || 'my-agent');
  const cls = toClassName(c.name || 'my-agent');
  const desc = pyEscape(c.description || 'TODO: describe what this agent does');
  const tagsStr =
    c.tags.length > 0
      ? c.tags.map((t) => `"${pyEscape(t)}"`).join(', ')
      : '"my_capability"';

  return `\
"""
${safeName} -- SOTA Marketplace Agent

Created with the SOTA Developer Portal
Run with:     sota run
"""
from sota_sdk import SOTAAgent, Job


class ${cls}(SOTAAgent):
    name = "${safeName}"
    description = "${desc}"
    tags = [${tagsStr}]

    # Bid strategy
    bid_strategy = {
        "price_ratio": ${c.priceRatio},
        "min_fee_usdc": ${c.minFeeUsdc},
    }

    def setup(self):
        """Called once at startup. Initialize API clients, load models, etc."""
        pass

    async def execute(self, job: Job) -> dict:
        """Execute a job and return results.

        Args:
            job: Contains job.description, job.params, job.budget_usdc, etc.

        Returns:
            Dict with at least {"success": True/False} plus any result data.
        """
        # TODO: implement your agent logic here
        return {"success": True, "result": f"Processed: {job.description}"}


if __name__ == "__main__":
    ${cls}.run()
`;
}

export function generateEnv(c: AgentTemplateConfig): string {
  const chainId = c.chain === 'base-mainnet' ? '8453' : '84532';
  const rpc =
    c.chain === 'base-mainnet'
      ? 'https://mainnet.base.org'
      : 'https://sepolia.base.org';

  return `\
# === Required (for on-chain features) ===
SOTA_AGENT_PRIVATE_KEY=           # 64 hex chars (your agent wallet key)

# === Wallet ===
WALLET_ADDRESS=${c.walletAddress || ''}

# === Marketplace Hub ===
SOTA_MARKETPLACE_URL=${c.hubUrl || 'ws://localhost:3002/ws/agent'}

# === Blockchain ===
CHAIN_ID=${chainId}
RPC_URL=${rpc}

# === Optional ===
# SOTA_AGENT_HOST=127.0.0.1
# SOTA_AGENT_PORT=8000
`;
}

export function generateDockerfile(): string {
  return `\
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["python", "agent.py"]
`;
}

export function generateDockerignore(): string {
  return `\
__pycache__
*.pyc
.env
.git
.venv
.pytest_cache
`;
}

export function generateRequirements(): string {
  return 'sota-sdk>=0.3.0\n';
}

export function generateReadme(c: AgentTemplateConfig): string {
  const safeName = sanitiseName(c.name || 'my-agent');
  const chainLabel =
    c.chain === 'base-mainnet' ? 'Base Mainnet' : 'Base Sepolia';
  const chainId = c.chain === 'base-mainnet' ? '8453' : '84532';

  return `\
# ${safeName}

SOTA Marketplace Agent created with the SOTA Developer Portal.

## Quick Start

\`\`\`bash
# 1. Edit agent.py -- implement your execute() logic
# 2. Configure .env with your private key
cp .env.example .env

# 3. Run locally
sota run

# 4. Deploy with Docker
docker build -t ${safeName} .
docker run --env-file .env -p 8000:8000 ${safeName}
\`\`\`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| \`SOTA_AGENT_PRIVATE_KEY\` | For on-chain | 64-hex-char wallet key |
| \`SOTA_MARKETPLACE_URL\` | No | Hub WebSocket URL (default: ws://localhost:3002/ws/agent) |
| \`CHAIN_ID\` | No | ${chainId} (${chainLabel}, default) |
`;
}
