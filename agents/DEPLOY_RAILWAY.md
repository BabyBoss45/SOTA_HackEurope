# Deploying All SOTA Agents to Railway

This guide deploys the Butler API + Marketplace Hub and all 7 agents as separate Railway services.

## Architecture

```
Railway Project
  |
  +-- sota-butler-api (port 3001) -- Hub mounted at /hub
  |     |
  |     +-- /hub/ws/agent   <-- agents connect here via WebSocket
  |     +-- /hub/jobs        <-- POST jobs, GET listings
  |     +-- /hub/agents      <-- GET connected agents
  |
  +-- sota-caller             (port 3003) --+
  +-- sota-hackathon          (port 3005) --|
  +-- sota-gift-suggestion    (port 3007) --|-- all connect to Hub
  +-- sota-restaurant-booker  (port 3008) --|   via internal networking
  +-- sota-refund-claim       (port 3009) --|
  +-- sota-smart-shopper      (port 3010) --|
  +-- sota-trip-planner       (port 3011) --+
```

## Step 1: Create Railway Project

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login and create project
railway login
railway init
```

## Step 2: Deploy Butler API (Hub)

This must be deployed first -- all agents connect to it.

```bash
railway service create sota-butler-api
```

**Settings in Railway Dashboard:**
- **Root Directory:** `agents`
- **Builder:** Dockerfile
- **Dockerfile Path:** `Dockerfile`
- **Start Command:** `python agents/butler_api.py`
- **Port:** `3001`

**Environment Variables:**
```
PORT=3001
RPC_URL=<your-solana-rpc-url>
PRIVATE_KEY=<butler-wallet-private-key>
PROGRAM_ID=<deployed-program-id>
USDC_MINT=<usdc-mint-address>
SOLANA_CLUSTER=devnet
ANTHROPIC_API_KEY=<your-api-key>
```

Deploy and note the **internal hostname** (e.g., `sota-butler-api.railway.internal`).

## Step 3: Deploy Each Agent

For each agent below, create a Railway service and configure it.

### Agent Service Table

| Service Name | Start Command | Port | Port Env Var |
|---|---|---|---|
| `sota-caller` | `python -m agents caller` | 3003 | `CALLER_PORT` |
| `sota-hackathon` | `python -m agents hackathon` | 3005 | `HACKATHON_AGENT_PORT` |
| `sota-gift-suggestion` | `python -m agents gift_suggestion` | 3007 | `GIFT_AGENT_PORT` |
| `sota-restaurant-booker` | `python -m agents restaurant_booker` | 3008 | `RESTAURANT_AGENT_PORT` |
| `sota-refund-claim` | `python -m agents refund_claim` | 3009 | `REFUND_AGENT_PORT` |
| `sota-smart-shopper` | `python -m agents smart_shopper` | 3010 | `SHOPPER_AGENT_PORT` |
| `sota-trip-planner` | `python -m agents trip_planner` | 3011 | `TRIP_AGENT_PORT` |

### For each agent service:

```bash
railway service create <service-name>
```

**Settings:**
- **Root Directory:** `agents`
- **Builder:** Dockerfile
- **Dockerfile Path:** `Dockerfile`
- **Start Command:** see table above

**Shared Environment Variables (set on ALL agent services):**
```
RPC_URL=<your-solana-rpc-url>
PROGRAM_ID=<deployed-program-id>
USDC_MINT=<usdc-mint-address>
SOLANA_CLUSTER=devnet
ANTHROPIC_API_KEY=<your-api-key>
SOTA_HUB_URL=ws://sota-butler-api.railway.internal:3001/hub/ws/agent
```

**Agent-specific variables:**

| Agent | Extra Env Vars |
|---|---|
| caller | `CALLER_PRIVATE_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` |
| hackathon | `HACKATHON_PRIVATE_KEY`, `SERPAPI_KEY` |
| gift_suggestion | `GIFT_PRIVATE_KEY`, `SERPAPI_KEY` |
| restaurant_booker | `RESTAURANT_PRIVATE_KEY`, `SERPAPI_KEY` |
| refund_claim | `REFUND_PRIVATE_KEY` |
| smart_shopper | `SHOPPER_PRIVATE_KEY`, `SERPAPI_KEY` |
| trip_planner | `TRIP_PRIVATE_KEY`, `SERPAPI_KEY` |

## Step 4: Verify Deployment

### Check Hub health:
```bash
curl https://<butler-api-url>/hub/health
# {"status": "ok", "connected_agents": 7, "active_jobs": 0}
```

### List connected agents:
```bash
curl https://<butler-api-url>/hub/agents
# Should show all 7 agents with their tags
```

### Check individual agent health:
```bash
curl https://<agent-url>/health
# {"status": "healthy", "agent": "<agent-name>"}
```

### Test a job:
```bash
curl -X POST https://<butler-api-url>/hub/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Find a restaurant in London for 4 people",
    "tags": ["restaurant_booking"],
    "budget_usdc": 5.0,
    "deadline_ts": 0,
    "poster": "test-user"
  }'
# Should return job_id and matched_agents > 0
```

## Troubleshooting

**Agent not appearing in /hub/agents:**
- Check the agent's logs for WebSocket connection errors
- Verify `SOTA_HUB_URL` is correct (use Railway internal networking)
- Ensure the Butler API service is running and healthy

**WebSocket connection refused:**
- The Butler API must be fully started before agents connect
- The HubConnector auto-reconnects with exponential backoff, so agents will eventually connect

**Agent not bidding on jobs:**
- Verify the job tags match the agent's supported job types
- Check the agent's logs for bid evaluation output
