# SOTA Backend Technical Documentation (v2)

This document provides an exhaustive technical reference for the SOTA platform rewrite (v2). It describes the architecture, every service boundary, all data flows, database schemas, smart contract designs, payment systems, monitoring infrastructure, shared utilities, and deployment configuration. Every section explains what each component does, why it was designed that way, and how it operates in detail, including edge cases, error handling, and validation rules.

---

## 1. Architecture Overview

### System Composition

The SOTA v2 platform is composed of four primary service boundaries: the FastAPI backend (Python), which hosts the Butler Agent and Marketplace Engine; the Supabase managed infrastructure layer, which provides PostgreSQL with pgvector for vector similarity search, Supabase Auth for user identity, and Supabase Realtime for low-latency pub/sub messaging; the Base L2 blockchain (an Ethereum Layer 2 network), which hosts Solidity smart contracts for escrow, agent registration, reputation tracking, dispute resolution, marketplace configuration, and payment routing; and the Vercel-hosted frontends, which include the mobile-first consumer application and the developer portal for agent publishers.

### ASCII System Diagram

    User (Voice / Chat / Mobile)
              |
              v
    +---------------------+
    |   Vercel Frontends   |
    |  (Next.js + Edge)    |
    +---------------------+
              |
              v
    +---------------------+        +----------------------+
    |   FastAPI Backend    | <----> |     Supabase         |
    |  - Butler Agent      |        |  - Postgres+pgvector |
    |  - Marketplace Engine|        |  - Auth              |
    |  - Agent SDK API     |        |  - Realtime channels |
    |  - Payment Router    |        |  - Storage           |
    +---------------------+        +----------------------+
              |                              |
              v                              v
    +---------------------+        +----------------------+
    |  Base L2 (Ethereum)  |        | External Agents      |
    |  - SOTAEscrow        |        | (3rd party via SDK)  |
    |  - SOTARegistry      |        +----------------------+
    |  - SOTAReputation    |
    |  - SOTAMarketplace   |
    |  - SOTADispute       |
    |  - SOTAPaymentRouter |
    +---------------------+

### Service Boundaries

The Butler Agent is the user-facing conversational interface. It interprets natural language requests, collects structured data through multi-turn slot filling, posts jobs to the marketplace, monitors execution, and relays results back to the user. It never executes tasks itself and never exposes marketplace terminology to the user.

The Marketplace Engine manages the lifecycle of jobs from creation through bidding, assignment, execution, and completion or failure. It broadcasts jobs to matching agents via Supabase Realtime channels, collects bids within a configurable time window, selects winners based on price and submission time, and coordinates escrow funding and payment release.

The Agent SDK provides an open REST protocol for third-party developers to register agents, subscribe to job channels, submit bids, execute tasks, and receive webhooks. It replaces the previous HMAC-based ClawBot protocol with a simpler API-key-based authentication scheme.

The Payment Router handles dual payment paths: Stripe for fiat users and Crossmint for crypto-native users. It routes funds into the on-chain escrow, manages surcharges for fiat on-ramping, and coordinates refunds across both Stripe and the blockchain.

### Data Flow

The complete data flow for a typical user request proceeds as follows. The user speaks or types a request through the mobile frontend or voice interface. The Butler Agent interprets the request using Claude (Anthropic's LLM) and begins multi-turn slot filling to collect structured parameters. Once the user confirms the gathered details, the Butler posts a job to the Marketplace Engine. The Marketplace Engine broadcasts the job to matching agents via Supabase Realtime channels named by tag, such as "marketplace:hackathon_registration" or "marketplace:restaurant_booking". Agents that are subscribed to those channels evaluate the job and submit bids within the bid window, which defaults to 15 seconds. The Marketplace Engine selects the winning bid using a lowest-price-first, earliest-submission tiebreaker algorithm. The user is prompted to fund the escrow through either Stripe or Crossmint. Once funded, the winning agent executes the task. During execution, the agent can request additional data from the user through the Butler (via agent data requests stored in the database). Upon completion, the agent submits results. The user confirms delivery, and the escrow releases payment to the agent minus the platform fee.

### Why This Architecture Was Chosen

Supabase replaces four separate infrastructure components from v1: Railway-hosted PostgreSQL, Prisma ORM, custom authentication, and Qdrant vector database. By consolidating into Supabase, the platform gains a managed PostgreSQL instance with built-in pgvector extension, Supabase Auth (eliminating custom JWT session management), Supabase Realtime (eliminating the need for a custom WebSocket server for bid broadcasting), and Supabase Storage (for file uploads and agent documentation). This reduces operational overhead, simplifies the deployment topology, and provides a unified dashboard for database, auth, and realtime monitoring. Specifically, pgvector replaces Qdrant for Butler RAG/memory search (see Section 2, rag_search tool). TaskPatternMemory's embedding-based similarity search for adaptive bidding (see Section 11) also migrates from Qdrant to pgvector in v2, though the v1 codebase still uses Qdrant for this. In v2, no Qdrant dependency remains.

Base (Ethereum L2) replaces Solana and the Anchor framework. The rationale is covered in detail in Section 8, but in summary: EVM compatibility provides access to a larger developer ecosystem, better wallet support for mainstream users through MetaMask and Coinbase Wallet, native USDC support from Circle, and lower gas costs than Ethereum mainnet while maintaining the security guarantees of Ethereum.

Vercel replaces Railway for frontend hosting. Vercel provides automatic HTTPS, edge CDN distribution, preview deployments for pull requests, and serverless functions for API routes. The FastAPI backend remains on a persistent hosting platform because it requires long-running connections for Supabase Realtime subscriptions and WebSocket handling, which do not fit the serverless execution model.

---

## 2. FastAPI Server

### Endpoint Map

The FastAPI server exposes the following REST endpoints, each mapped from the current butler_api.py to the v2 architecture.

POST /api/v1/chat accepts a JSON body containing a query string and an optional timestamp. It delegates to the Butler Agent's chat method, which runs the Anthropic Claude-backed agent loop with tool calling. The response includes a response text field containing the Butler's natural language reply and an optional job_posted field containing structured job data if the post_job tool was invoked during the conversation turn. The job_posted field, when present, contains the on-chain job ID, winning bid details, escrow information, and the amount in USDC, which the frontend uses to trigger the payment UI. The chat endpoint supports streaming responses via Server-Sent Events (SSE) using FastAPI's StreamingResponse. The SSE stream emits partial text tokens as they arrive from the LLM, followed by a final event containing the complete response and any job_posted data. This enables the frontend to display text as it is generated, providing a responsive user experience.

POST /api/v1/create handles job creation and escrow funding. It accepts a job description, tool type, parameters, and payment information. It creates the job record in Supabase, triggers the bidding process, and initiates escrow funding on Base L2.

POST /api/v1/status checks the current status of a job and whether delivery has been confirmed. It accepts a job_id and returns the job status, any agent updates, pending data requests, and whether delivery_confirmed is set on the escrow contract.

POST /api/v1/release triggers the release of escrowed payment to the winning agent. It requires that delivery has been confirmed by the user. It calls SOTAEscrow.releasePayment on Base L2, which transfers USDC to the agent's wallet minus the platform fee.

GET /api/v1/marketplace/jobs lists all marketplace jobs with optional status filtering. Returns an array of job objects sorted by creation time descending, with a default limit of 50.

GET /api/v1/marketplace/bids/{id} returns all bids submitted for a given job, including bidder identity, amount in USDC, estimated completion time in seconds, and submission timestamp.

GET /api/v1/marketplace/workers lists all registered worker agents with their status (online, offline, busy), capabilities, tags, reputation scores, and bidding configuration.

POST /api/v1/marketplace/post posts a new job to the marketplace. Accepts description, tags, budget_usdc, poster wallet address, and metadata containing tool type and parameters. Broadcasts the job to matching Supabase Realtime channels and opens the bid window.

POST /api/v1/marketplace/execute/{job_id} called by the winning agent to submit execution results. Requires API key authentication. Validates that the requesting agent is the assigned winner and that the job is in "assigned" status. Updates the job status, creates an AgentJobUpdate record, increments the agent's execution statistics, and fires a webhook notification to the agent's registered webhook_url.

### Middleware

CORS middleware is configured to allow all origins during development and a specific allowlist in production. Request logging middleware logs every incoming request with method, path, status code, and response time. Error handling middleware catches unhandled exceptions, logs them with full stack traces, and returns structured JSON error responses with appropriate HTTP status codes. In v2, Sentry integration captures all unhandled exceptions and slow transactions automatically.

### Startup and Shutdown

On startup, the server initializes the Supabase client using SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables. It loads the Butler Agent, which initializes the Anthropic Claude client, creates the tool manager with all Butler tools, and establishes the system prompt. It connects to the Base L2 RPC endpoint for on-chain operations. It subscribes to relevant Supabase Realtime channels for marketplace event broadcasting.

On shutdown, the server performs a graceful shutdown sequence. It closes all active Supabase Realtime subscriptions, drains any in-flight SSE streams, closes the Supabase connection pool, and logs the shutdown event.

### Hybrid REST and WebSocket Architecture

The v2 architecture uses a hybrid approach. REST endpoints handle all CRUD operations: creating jobs, listing bids, checking status, releasing payments, and registering agents. Supabase Realtime channels handle low-latency event broadcasting: job availability notifications to agents, bid submissions, status updates during execution, and result delivery notifications. This separation was chosen because REST provides a simple, well-understood interface for operations that do not require real-time delivery, while Supabase Realtime provides instant delivery for time-sensitive operations like bid broadcasting (where the 15-second default window makes even a few hundred milliseconds of latency significant).

### Streaming Chat Response

The chat endpoint implements SSE streaming for the Butler's responses. When a client sends a POST to /api/v1/chat, the server creates a StreamingResponse with content type "text/event-stream". As the Claude LLM generates text tokens, each token is emitted as an SSE event with a "data:" prefix. When the LLM invokes a tool (such as post_job), the tool execution happens server-side, and the tool result is fed back to the LLM for the next generation step. The final SSE event includes the complete response text and, if post_job was called, the job_posted JSON structure. The frontend parses this final event to detect whether a payment flow should be triggered.

The job_posted JSON structure, when embedded in the chat response, contains the following fields: success (boolean), on_chain_job_id (integer), job_id (UUID string), winning_bid (object with agent name, amount_usdc, and eta_seconds), escrow_address (the Base contract address), and amount_usdc (the bid amount that needs to be funded). The frontend uses this data to render the Stripe or Crossmint payment widget with the correct amount and metadata.

---

## 3. Butler Agent

### System Prompt Design Philosophy

The Butler Agent's system prompt is designed around a single principle: the user should feel like they are interacting with a warm, professional personal assistant, not a marketplace platform. The Butler never uses words like "job", "bid", "worker", "marketplace", "slot", "USDC", or any other technical term. Instead, it uses natural language equivalents: "I'll find someone for that", "looking for the best specialist", "I've got someone working on it", "estimated time: about 2 minutes". The tone is modeled after a luxury hotel concierge: friendly, concise, and professional.

The system prompt enforces a strict workflow sequence. First, the Butler understands the request by calling fill_slots to collect structured data. If information is missing, it asks a natural follow-up question and stops, waiting for the user's response. Once all required data is gathered, it summarizes the details and asks for confirmation. Second, upon user confirmation, the Butler immediately calls the post_job tool function. The system prompt explicitly prohibits the LLM from outputting JSON as text instead of making a function call, labeling this as a "VIOLATION". Third, after post_job returns, the Butler reports back in natural language without exposing any internal identifiers or marketplace mechanics.

### Tool Definitions

Each Butler tool is implemented as a subclass of BaseTool, which defines a name, description, parameters JSON schema, and an async execute method. The tools are registered with a ToolManager instance, which converts them to Anthropic tool-calling format and dispatches calls by name.

**fill_slots**: This tool performs multi-turn slot filling to collect structured data for a task. It accepts a slot schema as input, which defines the required and optional fields for a given task type. For example, a hackathon registration task requires time_period, location, topics, and mode. The tool validates that all required fields are populated, identifies missing fields, and generates natural follow-up questions for the Butler to ask the user. The output is a dictionary of filled slot values. If required fields are missing, the output includes a list of missing fields with suggested questions. Error handling covers invalid slot schemas (returns a descriptive error), partially filled slots (returns the filled values plus the missing list), and type validation failures (coerces where possible, reports where not).

**post_job**: This tool submits a job to the marketplace. It builds a job description, tags, and parameters from the filled slots. It must only be called after the user has explicitly confirmed the gathered details. The input includes a natural language description of the task, a tool type string (such as "hackathon_registration", "restaurant_booking", "smart_shopping", "trip_planning"), and a parameters object containing the structured data collected during slot filling. The tool creates the job in the database, broadcasts it to matching Supabase Realtime channels, waits for the bid window to close (default 15 seconds, configurable up to 300 seconds), selects the winning bid, and returns a result object containing success status, on_chain_job_id, job_id (UUID), winning_bid details (agent name, amount_usdc, eta_seconds), and escrow information. If no valid bids are received within the window, the job expires and the tool returns success=false with a reason string. Error handling covers database write failures (retried once, then returned as an error), Realtime broadcast failures (job is still created in the database but agents may not see it), and bid window timeout with no bids (job status set to "expired").

**check_agent_requests**: This tool polls for pending data requests from the worker agent that is currently executing a job. Worker agents can request additional information from the user, such as their email address for hackathon registration, phone number for a booking confirmation, or clarification on ambiguous requirements. The tool queries the AgentDataRequest table for records with status "pending" and returns a list of pending requests, each containing a request_id, the requesting agent's name, the data_type (one of: user_profile, preference, confirmation, clarification, custom), the question text, the specific fields needed, and optional context. If no pending requests exist, it returns an empty list. Error handling covers database connection failures (returns an error message suggesting a retry).

**answer_agent_request**: This tool sends the user's response back to the requesting worker agent. It accepts a request_id and the user's answer data (a dictionary of field values or a confirmation message). It updates the AgentDataRequest record's status to "answered", stores the answer_data and answer_msg, and sets the answered_at timestamp. The worker agent polls for answered requests and continues execution. Error handling covers invalid request_id (returns a "request not found" error), already-answered requests (returns an idempotent success with the existing answer), and malformed answer_data (validates that required fields from the original request are present).

**get_agent_updates**: This tool retrieves progress updates from the executing worker agent. It queries the AgentJobUpdate table for records matching the current job_id, ordered by creation time. Each update contains the agent's name, a status string (in_progress, partial_result, completed, error), a human-readable message, optional structured data, and a timestamp. The Butler uses these updates to keep the user informed about progress without exposing internal details. Error handling covers jobs with no updates (returns an empty list with a message that work is still in progress).

**rag_search**: This tool queries pgvector for relevant context from the Butler's memory. In v2, this replaces the previous Qdrant and Mem0 integration. The Butler stores conversation summaries and user preferences as embeddings in Supabase pgvector (using the embedding column on the user_profiles table with vector dimension 1536). When the Butler needs to personalize a response or recall past interactions, it calls rag_search with a natural language query. The tool embeds the query using the same embedding model, performs a cosine similarity search against stored embeddings, and returns the top matching results with their similarity scores. This enables the Butler to remember user preferences (such as preferred cuisines, travel styles, or past hackathon interests) across sessions without asking repetitive questions. Error handling covers embedding model failures (returns an empty result set with a warning), pgvector query failures (returns a graceful degradation message), and cases where no similar embeddings exist above the similarity threshold (returns an empty set).

### Job Dispatch Flow

The complete job dispatch flow proceeds through these stages: fill_slots gathers structured parameters through one or more conversation turns. The Butler summarizes the gathered data and asks for user confirmation. Upon confirmation, post_job is called. The job is created in the database and broadcast to matching Supabase Realtime channels. The bid window opens (default 15 seconds, configurable via bid_window_seconds in the job metadata). Agents evaluate the job and submit bids. When the bid window closes, the Marketplace Engine selects the winner (lowest price, earliest submission as tiebreaker). The escrow funding is initiated (user pays via Stripe or Crossmint). Once funded, the winning agent begins execution. The Butler monitors execution by periodically calling check_agent_requests and get_agent_updates. When the agent completes, the result is delivered to the user. The user confirms delivery, and payment is released from escrow.

### Conversation Management

Conversations are stored in Supabase in the chat_sessions and chat_messages tables. Each session is identified by a UUID and optionally associated with a wallet address and/or user_id. Messages within a session are persisted with role (user, assistant, or system), text content, and a creation timestamp. Sessions are filterable by wallet address or user_id, enabling the Butler to maintain conversation continuity across devices. The Butler Agent maintains an in-memory conversation_history list during a session, which is passed to the LLM as context for each new message. This history is also persisted to the database for durability.

### pgvector Memory

In v2, the Butler's long-term memory uses Supabase pgvector instead of a separate Qdrant instance. The user_profiles table includes an embedding column of type vector(1536) that stores conversation summaries and user preference vectors. When the Butler completes a conversation, it generates a summary embedding and stores it alongside the user profile. On subsequent interactions, the Butler queries pgvector for similar past interactions to personalize responses. For example, if a user previously searched for AI hackathons in Europe, the Butler can proactively mention relevant upcoming events without being asked. The embedding model used for vectorization produces 1536-dimensional vectors, matching the pgvector column size.

### Safety Net: JSON Interception

The Butler Agent includes a safety net mechanism to handle cases where the LLM outputs JSON as text instead of making a proper post_job function call. This can happen occasionally due to prompt adherence variability. The safety net uses regular expression matching to detect JSON structures in the LLM's text response that look like job definitions (containing keys like "job", "tool", "description", "location", "theme", or "parameters"). If detected, the safety net extracts the JSON, constructs post_job arguments from it, calls post_job programmatically, and replaces the raw JSON response with a natural language confirmation message. This ensures the user never sees raw JSON and the job is always properly posted to the marketplace.

---

## 4. Marketplace Engine

### Job Lifecycle

Jobs move through the following states, each with specific triggers and behaviors.

OPEN: The initial state when a job is created via POST /api/v1/marketplace/post or the post_job Butler tool. The job record is written to the database with status "open", a UUID job_id, description, tags, budget in USDC, poster wallet address, and metadata containing the tool type and parameters. The createdAt and updatedAt timestamps are set. No bids exist yet.

BIDDING: Immediately after creation, the job transitions to "bidding" status. The Marketplace Engine broadcasts the job to Supabase Realtime channels matching the job's tags. For example, a job tagged "hackathon_registration" is broadcast on the "marketplace:hackathon_registration" channel. The bid window opens, with its duration set by bid_window_seconds (default 15, maximum 300). Agents subscribed to matching channels receive the job_available event and begin evaluating whether to bid.

SELECTING: When the bid window closes, the job transitions to "selecting" status. The Marketplace Engine evaluates all received bids using the selection algorithm described below. This state is transient, typically lasting only milliseconds.

ASSIGNED: After the winner is selected, the job transitions to "assigned" status. The winner field is set to the winning agent's identifier, and winner_price is set to the bid amount. The winning agent receives a bid_accepted notification via Supabase Realtime and a webhook POST to its registered webhook_url. All losing bidders receive bid_rejected notifications. The job now waits for escrow funding and then execution.

EXECUTING: Once the escrow is funded and the agent begins work, the job transitions to "executing" status. The agent can create AgentDataRequest records to request additional information from the user (via the Butler). The agent can create AgentJobUpdate records to report progress. The Butler polls for these records using check_agent_requests and get_agent_updates.

COMPLETED: When the agent submits a successful result via POST /api/v1/marketplace/execute/{job_id} with status "completed", the job transitions to "completed". An AgentJobUpdate record is created with the result data. The agent's statistics are incremented (totalRequests and successfulRequests). The user can now confirm delivery to release payment.

FAILED: If the agent submits a result with status other than "completed", or if execution raises an unrecoverable error, the job transitions to "failed". The agent's totalRequests is incremented but successfulRequests is not. A refund process may be initiated.

EXPIRED: If no valid bids are received within the bid window, the job transitions to "expired" with a reason field explaining why (typically "no bids received within window").

CANCELLED: If the user or an admin cancels a job before completion, it transitions to "cancelled". If the escrow was already funded, a refund is initiated.

### Bidding Protocol

When a job is posted, the Marketplace Engine broadcasts it to agents via Supabase Realtime channels. Each agent type subscribes to channels matching its capabilities. For example, the Hackathon Agent subscribes to the "marketplace:hackathon_registration" channel. The Restaurant Booker subscribes to "marketplace:restaurant_booking" and "marketplace:restaurant_booking_smart". Agents have a configurable bid window to evaluate the job and submit bids.

Each agent's evaluation logic (implemented in the _evaluate_job_for_board method of the AutoBidderMixin) performs the following checks. First, it compares the job's tags against the agent's supported job type tags. If there is no overlap, the agent does not bid. Second, it checks whether the agent is at capacity (active jobs versus max_concurrent_jobs). If at capacity, it does not bid. Third, it calculates a bid price using the bid_price_ratio multiplied by the job's budget, with a floor of 0.50 USDC. Fourth, if task_memory is available, it performs adaptive bidding analysis (described below). Finally, it creates a Bid object with a random 8-character bid_id, the job_id, the agent's identity and wallet address, the calculated amount in USDC, and the estimated completion time in seconds.

### Supabase Realtime for Low-Latency Bidding

Supabase Realtime was chosen over raw WebSocket implementation for several reasons. It provides built-in authentication, meaning agents must authenticate with their Supabase credentials before subscribing to channels, preventing unauthorized bid submissions. It provides presence tracking, which allows the Marketplace Engine to know which agents are currently online and subscribed. It provides channel-based pub/sub, which maps cleanly to the tag-based job routing model. And it requires no custom WebSocket server, because Supabase manages the WebSocket infrastructure, connection handling, reconnection logic, and message delivery guarantees.

Jobs are broadcast on channels named by tag, following the pattern "marketplace:{tag}". For example, "marketplace:hackathon_registration", "marketplace:restaurant_booking", "marketplace:trip_planning". When a job has multiple tags, it is broadcast on all matching channels. Agents subscribe to channels matching their capabilities during registration. Bid submissions, status updates, and results all flow through Realtime for instant delivery. This ensures that the 15-second default bid window is sufficient for agents to receive the broadcast, evaluate the job, and submit a bid, even with globally distributed agents.

### Bid Selection Algorithm

When the bid window closes, the Marketplace Engine selects the winning bid using the following algorithm.

Step 1: Filter bids where amount_usdc is less than or equal to the job's budget_usdc. Bids that exceed the budget are discarded. This prevents agents from bidding above the user's stated budget.

Step 2: Sort remaining bids by (amount_usdc ascending, submitted_at ascending). The lowest price wins. If two bids have the same price, the one submitted earliest wins. This incentivizes agents to bid competitively and quickly.

Step 3: If no valid bids remain after filtering, the job expires with reason "no valid bids within budget" or "no bids received within window".

Step 4: The first bid in the sorted list is the winner. The winning agent receives a bid_accepted notification containing the job details and confirmed bid amount. All other bidders receive bid_rejected notifications.

### Adaptive Bidding System

Agents can analyze past task outcomes to adjust their bidding strategy using the TaskPatternMemory system. Before evaluating a new job, the agent queries its task_memory for similar past tasks using embedding-based similarity search. The analysis returns a PatternAnalysis object containing: the number of similar past outcomes, the historical success rate for similar tasks, common failure types, average execution time, a confidence score (computed as success_rate multiplied by mean_similarity_score), and a recommended_strategy string.

The recommended strategy is determined by the confidence score: 0.6 or above yields "standard" (normal bidding), 0.3 to 0.6 yields "cautious" (bid 1.3x higher to account for risk, increase ETA by 50%), 0.15 to 0.3 yields "human_assisted" (bid higher, flag for human review), and below 0.15 yields "decline" (the agent skips the job entirely). When confidence is below 0.5 and there are similar historical outcomes, the bid price is multiplied by 1.3 and the ETA is multiplied by 1.5, reflecting the higher risk and expected longer execution time.

### REST API for Job Management

In addition to the Supabase Realtime-based bidding, the Marketplace Engine provides REST endpoints for all CRUD operations on jobs. GET /api/v1/marketplace/jobs supports optional status filtering and pagination. GET /api/v1/marketplace/bids/{id} returns all bids for a specific job. GET /api/v1/marketplace/workers returns all registered agents with their current status and capabilities. POST /api/v1/marketplace/post creates new jobs. POST /api/v1/marketplace/execute/{job_id} allows agents to submit results. These REST endpoints serve as the authoritative API for marketplace operations, while Realtime handles the time-sensitive event broadcasting.

---

## 5. Agent SDK (Open Protocol)

### Design Philosophy

Version 2 replaces the ClawBot HMAC-based protocol with an open REST protocol. The previous protocol required agents to sign every request with an HMAC-SHA256 signature using a shared secret, which added complexity for developers (they needed an SDK library in their language to compute the signature correctly), made debugging difficult (signature mismatches produced opaque errors), and limited participation to languages with good HMAC libraries. The new protocol uses standard API key authentication in the Authorization header, which is language-agnostic: any language or framework that can make HTTP requests and set headers can participate.

### Registration

To register a new agent, a developer sends a POST request to /api/v1/agents/register with the following fields: name (the agent's display name), description (what the agent does), capabilities (an array of strings like "hackathon_search", "web_scraping", "voice_call"), wallet_address (the agent's Base L2 wallet address for receiving payments), api_endpoint (the URL where the SOTA platform can send execution requests), and webhook_url (the URL where the SOTA platform sends event notifications). The registration endpoint creates an ExternalAgent record with status "pending", generates an API key pair (a public key_id like "ak_7f3b2e..." and the raw key), SHA-256 hashes the raw key for storage (the raw key is never stored in plaintext), creates an AgentApiKey record linking the key to the agent, and returns the agent_id (UUID), the raw API key (shown only once), and the public key_id.

### Authentication

All authenticated SDK endpoints require the API key in the Authorization header using the Bearer scheme: "Authorization: Bearer ak_7f3b2e4a9c...". On each request, the server extracts the key from the header, computes its SHA-256 hash, looks up the hash in the AgentApiKey table, verifies the key is active (isActive is true), has not expired (expiresAt is null or in the future), and has the required permission for the requested operation. The lastUsedAt timestamp is updated on every successful authentication.

API key permissions are defined as an array of strings. The available permissions are: "execute" (allows submitting job execution results), "bid" (allows placing bids on jobs), "read" (allows reading job listings and marketplace data), and "admin" (allows managing agent settings and generating additional API keys). The default permissions for a new key are "execute" and "bid".

### Bidding

In v2, agents subscribe to Supabase Realtime channels matching their registered capabilities. When a job_available event arrives on a subscribed channel, the agent evaluates the job and, if interested, POSTs a bid to /api/v1/marketplace/bid with the following fields: job_id (the UUID of the job), amount_usdc (the bid amount in USDC), and estimated_seconds (the expected time to complete the task). The bid endpoint validates the API key, verifies the agent has "bid" permission, checks that the bid window is still open, and records the bid in the Bids table with the agent's identity and a submitted_at timestamp.

### Execution

When an agent wins a bid, it receives a bid_accepted notification via two channels: a Supabase Realtime event on the agent's channel, and a webhook POST to the agent's registered webhook_url. Both contain the job details (job_id, description, tags, metadata, budget, and confirmed bid amount). The agent performs the task and submits the result by POSTing to /api/v1/marketplace/execute with job_id, result (the structured result data as a JSON object), and a success flag (boolean). The endpoint validates that the requesting agent is the assigned winner and that the job is in "assigned" status. On success, the job status is updated, an AgentJobUpdate record is created, and the agent's statistics are incremented.

### Webhook Specification

The SOTA platform sends POST requests to each agent's registered webhook_url for the following events. Each webhook payload includes event_type (string), job_id (UUID string), timestamp (ISO 8601 string), and event-specific data fields.

Event "job_assigned": Sent when the agent wins a bid. Additional fields include description, tags, metadata, budget_usdc, and confirmed_amount_usdc.

Event "job_cancelled": Sent when a job the agent was assigned to is cancelled. Additional fields include reason and refund_initiated (boolean).

Event "payment_released": Sent when the escrow payment is released to the agent's wallet. Additional fields include amount_usdc, platform_fee_usdc, net_amount_usdc, and tx_hash (the Base L2 transaction hash).

Event "dispute_raised": Sent when a dispute is raised against the agent for a job. Additional fields include raised_by (wallet address), reason, and dispute_id.

Webhook delivery is fire-and-forget. If the agent's webhook endpoint is unreachable, the event is logged but not retried. Agents that require reliable event delivery should also subscribe to Supabase Realtime channels as a complementary notification path.

### Why Open REST Over HMAC

The decision to replace HMAC with API key authentication was driven by four factors. Lower barrier to entry: developers can test the API with curl or Postman without needing to implement HMAC signature computation. No SDK required: while HMAC authentication practically requires an SDK library to compute signatures correctly (with proper canonical request formatting, timestamp handling, and header ordering), API key authentication works with any HTTP client. Easier debugging: API key errors produce clear messages ("invalid key", "expired key", "insufficient permissions") instead of opaque signature mismatch errors. Language and framework compatibility: API keys work identically in every programming language, framework, and HTTP client, making the SOTA marketplace accessible to the widest possible developer audience.

---

## 6. Specialist Agents (Test/Demo)

These agents exist for testing and demonstration purposes. In v2, the expectation is that real production agents will come from third-party developers via the Agent SDK. Each agent listed here serves as a reference implementation that demonstrates the patterns and capabilities that external agents can replicate.

### Butler Agent

The Butler Agent is the user-facing interface and is not a worker agent. It does not bid on jobs and does not execute tasks. Its sole purpose is to orchestrate: understanding user requests, collecting structured data, posting jobs, monitoring execution, and relaying results. Its system prompt, tools, and conversation management are described in detail in Section 3.

### Hackathon Agent

Purpose: Finds upcoming hackathons and coding competitions and optionally registers users for them. Supported job types: HACKATHON_REGISTRATION. Bidding config: bid_price_ratio of 0.70 (bids 70% of budget because hackathon search is computationally cheap), bid_eta_seconds of 120 (approximately 2 minutes to search and format results), max_concurrent_jobs of 5. The agent's system prompt enforces a golden rule: never show or return past hackathons. Every result must have a start date on or after today. If a search returns past events, the agent silently drops them.

Key tools include search_hackathons (searches the internet for upcoming hackathons by location, date range, keywords, and mode), scrape_hackathon_details (scrapes event pages for detailed information including registration links, prizes, and sponsors), filter_hackathons (applies additional filters to narrow results), detect_registration_form (analyzes a hackathon URL to identify registration form fields), and auto_fill_and_register (fills registration forms with user profile data, always using dry_run=true first to preview before submitting). The agent communicates with the Butler via request_butler_data (to request user profile information, clarification, or confirmation) and notify_butler (to send progress updates). The system prompt includes a fallback mechanism: if the LLM fails to return results, the agent bypasses the LLM and calls the search tool directly as a fallback, also trying event_finder scrapers.

### Restaurant Booker

Purpose: Finds restaurants matching user preferences. The restaurant booker never makes reservations directly and never handles payments. It learns the user's cuisine preferences over time through the rag_search memory system. When a booking is needed, it provides the restaurant's phone number so the Caller agent can make the reservation call. This separation of concerns ensures that payment-sensitive operations are handled by specialized agents with appropriate verification.

### Trip Planner

Purpose: Group trip planning with an "intelligence over friction" philosophy. The agent infers parameters from the user's profile rather than asking every question. It uses a confidence threshold: only fields where the agent's confidence in the inferred value is below 0.6 are asked about explicitly. For example, if the user's profile indicates they live in London and prefer budget travel, the agent infers departure city and accommodation class without asking.

Key tools include infer_from_profile (analyzes user profile data and conversation history to infer travel preferences with confidence scores), search_flights (searches for flights matching criteria), search_accommodation (searches for hotels and accommodations), and build_itinerary (assembles a coherent multi-day itinerary from flights, accommodation, and activities).

### Smart Shopper

Purpose: Price comparison with economic reasoning. The Smart Shopper never purchases anything. It analyzes price trends, stock levels, and market conditions to recommend whether to buy now or wait. Key tools include search_retailers (searches multiple retailers for product availability and pricing), track_price_history (retrieves historical price data for a product to identify trends), and analyze_market (performs economic analysis combining price trends, stock levels, seasonal patterns, and competitor pricing to produce a buy/wait recommendation with supporting rationale).

### Caller Agent

Purpose: Phone call verification and bookings via ElevenLabs voice synthesis. The Caller agent makes actual phone calls using the ElevenLabs Conversational AI API. It is used when another agent needs voice verification (confirming a restaurant reservation, verifying availability, etc.). The call results are stored in the CallSummary table with conversation_id, call_sid, status, summary, to_number, job_id, storage_uri (for call recordings), and a payload JSON containing the full call data.

### Gift Suggestion Agent

Purpose: Personalized gift recommendations based on recipient profile, occasion, budget, and relationship. Uses the user profile and conversation history to understand the recipient's interests and preferences.

### Refund Claim Agent

Purpose: Automated refund processing. Helps users navigate refund processes for various services by gathering order details, identifying the refund policy, and guiding the user through the claim process.

### Fun Activity Finder

Purpose: Event and activity search with preference learning. Finds concerts, exhibitions, sports events, outdoor activities, and other entertainment options. Learns the user's preferences over time (music genres, activity types, preferred times, budget range) and uses this learned profile to rank and filter results.

---

## 7. Database (Supabase)

Version 2 uses Supabase as the unified database layer, replacing the previous Railway-hosted PostgreSQL with Prisma ORM. Supabase provides managed PostgreSQL with the pgvector extension for vector similarity search, Supabase Auth for user identity management, and Supabase Realtime for pub/sub messaging. The following schema describes all tables with their columns, types, constraints, indexes, and relationships.

### Users Table

This table extends Supabase auth.users with profile data. Supabase Auth manages the core authentication fields (email, password hash, OAuth tokens). The Users table adds application-specific fields.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | Primary key | Matches auth.users.id |
| email | text | Unique, not null | User's email address |
| password_hash | text | Not null, default "" | Argon2 hash (managed by Supabase Auth) |
| name | text | Nullable | Display name |
| wallet_address | text | Nullable | Base L2 wallet address for wallet linking |
| role | text | Default "user" | User role: "user", "developer", "admin" |
| avatar_url | text | Nullable | Profile avatar URL |
| created_at | timestamptz | Default now() | Account creation timestamp |

Index on email for fast lookup during authentication. Supabase Auth handles email/password authentication, OAuth flows (Google, GitHub), and JWT token issuance. The wallet_address field enables linking a Base L2 wallet to the user's account for crypto payments.

### Agents Table

Stores agent listings in the marketplace, including both internal reference agents and externally registered agents from developers.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| title | text | Not null | Agent display name |
| description | text | Not null | What the agent does |
| category | text | Nullable | Agent category for marketplace browsing |
| price_usd | numeric | Default 0 | Listed price in USD |
| status | text | Default "active" | Listing status: "active", "inactive", "suspended" |
| tags | text[] | Nullable | Capability tags as an array |
| network | text | Default "base-sepolia" | Blockchain network the agent operates on |
| image | text | Nullable | Agent listing image URL |
| wallet_address | text | Nullable | Agent's Base L2 payment wallet address |
| owner_id | UUID | FK to users.id | The developer who owns this agent |
| api_endpoint | text | Nullable | URL for sending execution requests |
| api_key_hash | text | Nullable | SHA-256 hash of the agent's API key |
| capabilities | jsonb | Nullable | JSON array of capability strings |
| webhook_url | text | Nullable | Callback URL for async event notifications |
| onchain_address | text | Nullable | Base L2 contract address for this agent |
| is_verified | boolean | Default false | Whether the platform has verified this agent |
| documentation | text | Nullable | Agent documentation in markdown format |
| min_fee_usdc | numeric | Default 0.01 | Minimum fee per API call in USDC |
| max_concurrent | int | Default 5 | Maximum concurrent jobs |
| bid_aggressiveness | numeric | Default 0.8 | Multiplier for bid pricing (0.5 to 1.0) |
| total_requests | int | Default 0 | Total jobs executed |
| successful_requests | int | Default 0 | Successfully completed jobs |
| reputation | numeric | Default 5.0 | Rating from 0 to 5 |
| icon | text | Nullable | Lucide icon name for UI display |
| created_at | timestamptz | Default now() | Record creation |
| updated_at | timestamptz | Auto-updated | Last modification |

Indexes on owner_id (for listing a developer's agents), status (for filtering active agents), and wallet_address (for payment routing).

### Jobs Table

Stores marketplace jobs with their full lifecycle data.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| job_id | UUID | Unique, not null | Public identifier used in all API operations |
| description | text | Not null | Natural language job description |
| tags | text[] | Not null | Tags for routing to matching agents |
| budget_usdc | numeric | Default 0 | Maximum budget in USDC |
| status | text | Default "open" | Lifecycle state (see Section 4) |
| poster | text | Nullable | Wallet address of the job poster |
| winner | text | Nullable | Identifier of the winning agent |
| winner_price | numeric | Nullable | Accepted bid amount in USDC |
| metadata | jsonb | Nullable | Tool type, parameters, and other structured data |
| bid_window_seconds | int | Default 15 | Duration of the bidding window |
| created_at | timestamptz | Default now() | Job creation |
| updated_at | timestamptz | Auto-updated | Last status change |

Indexes on job_id (primary lookup key), status (for filtering by lifecycle state), and poster (for listing a user's jobs).

### Bids Table

Stores bids submitted by agents for marketplace jobs.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| bid_id | UUID | Unique | Public bid identifier |
| job_id | UUID | FK to jobs.job_id | The job being bid on |
| agent_id | text | Not null | The bidding agent's identifier |
| agent_name | text | Nullable | Display name of the bidding agent |
| wallet_address | text | Nullable | Agent's payment wallet address |
| amount_usdc | numeric | Not null | Bid amount in USDC |
| estimated_seconds | int | Nullable | Estimated completion time |
| submitted_at | timestamptz | Default now() | When the bid was submitted |

Indexes on job_id (for retrieving all bids for a job) and agent_id (for retrieving an agent's bid history).

### Orders Table

Tracks payment transactions linking agents to buyers.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| agent_id | int | FK to agents.id | The agent involved |
| buyer_id | UUID | FK to users.id, nullable | The purchasing user |
| tx_hash | text | Not null | Blockchain transaction hash |
| amount_usdc | numeric | Not null | Transaction amount in USDC |
| network | text | Not null | Blockchain network (e.g., "base-sepolia") |
| wallet_address | text | Not null | Wallet address involved |
| created_at | timestamptz | Default now() | Transaction timestamp |

### Worker Agents Table

Persistent registry for internal and SDK-registered worker agents. This table tracks agent status, capabilities, bidding configuration, and performance statistics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| worker_id | text | Unique | Stable identifier (e.g., "hackathon", "caller") |
| name | text | Not null | Display name |
| description | text | Nullable | What the agent does |
| tags | text[] | Not null | Job type tags the agent responds to |
| version | text | Default "1.0.0" | Agent version string |
| wallet_address | text | Nullable | Base L2 payment wallet |
| capabilities | text[] | Not null | Capability strings |
| status | text | Default "offline" | Current status: "online", "offline", "busy" |
| last_heartbeat | timestamptz | Nullable | Last heartbeat timestamp |
| connected_at | timestamptz | Nullable | When the agent connected |
| total_jobs | int | Default 0 | Total jobs executed |
| successful_jobs | int | Default 0 | Successfully completed jobs |
| failed_jobs | int | Default 0 | Failed jobs |
| total_earnings_usdc | numeric | Default 0 | Cumulative earnings |
| reputation | numeric | Default 5.0 | Rating from 0 to 5 |
| max_concurrent | int | Default 5 | Maximum concurrent jobs |
| bid_price_ratio | numeric | Default 0.80 | Multiplier for bid pricing |
| bid_eta_seconds | int | Default 1800 | Default estimated completion time |
| min_profit_margin | numeric | Default 0.1 | Minimum acceptable profit margin |
| icon | text | Nullable | Lucide icon name |
| metadata | jsonb | Nullable | Additional structured data |
| api_endpoint | text | Nullable | Agent's API endpoint URL |
| source | text | Default "sdk" | Origin: "sdk" for external, "internal" for built-in |
| created_at | timestamptz | Default now() | Registration time |
| updated_at | timestamptz | Auto-updated | Last update |

Indexes on status (for filtering online agents) and wallet_address (for payment routing). The upsert operation (used during agent registration and reconnection) preserves statistics (total_jobs, successful_jobs, failed_jobs, total_earnings_usdc) on conflict, only updating mutable fields like status, version, and heartbeat timestamps.

### External Agents Table

Stores agents registered through the external developer marketplace (the ClawBot protocol and its v2 successor).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| agent_id | UUID | Unique, default gen_random_uuid() | Public agent identifier |
| name | text | Not null | Agent name |
| description | text | Not null | Agent description |
| endpoint | text | Not null | Must be HTTPS URL |
| capabilities | text[] | Not null | Capability strings |
| supported_domains | text[] | Not null | Supported web domains |
| wallet_address | text | Not null | Base L2 wallet address |
| public_key | text | Nullable | Encrypted signing key (legacy HMAC) |
| status | text | Default "pending" | Lifecycle: "pending", "verifying", "active", "suspended", "banned" |
| verified_at | timestamptz | Nullable | When verification completed |
| created_at | timestamptz | Default now() | Registration time |
| updated_at | timestamptz | Auto-updated | Last update |

Indexes on status and wallet_address.

### Chat Sessions Table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | Primary key, default gen_random_uuid() | Session identifier |
| wallet | text | Nullable | User's wallet address |
| user_id | UUID | Nullable, FK to users.id | Authenticated user ID |
| title | text | Nullable | Conversation title (auto-generated or user-set) |
| created_at | timestamptz | Default now() | Session start |
| updated_at | timestamptz | Auto-updated | Last activity |

### Chat Messages Table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| session_id | UUID | FK to chat_sessions.id | Parent session |
| role | text | Not null | Message role: "user", "assistant", "system" |
| text | text | Not null | Message content |
| created_at | timestamptz | Default now() | Message timestamp |

Index on session_id for efficient conversation retrieval.

### Execution Tokens Table

Short-lived tokens for authorizing agent execution of specific jobs.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| token | UUID | Unique, default gen_random_uuid() | The execution token |
| job_id | text | Not null | Associated job |
| agent_id | text | FK to external_agents.agent_id | Authorized agent |
| expires_at | timestamptz | Not null | Token expiration |
| used | boolean | Default false | Whether the token has been consumed |
| used_at | timestamptz | Nullable | When the token was used |
| confidence_submitted | numeric | Nullable | Agent's confidence score for the result |
| created_at | timestamptz | Default now() | Token creation |

Indexes on token (for fast lookup), job_id, and agent_id.

### Agent Data Requests Table

Stores requests from executing agents for additional data from the user (relayed through the Butler).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| request_id | text | Unique | Short UUID for identification |
| job_id | text | FK to jobs.job_id | Associated job |
| agent | text | Not null | Requesting agent identifier |
| data_type | text | Not null | Request type: "user_profile", "preference", "confirmation", "clarification", "custom" |
| question | text | Not null | Human-readable question for the user |
| fields | text[] | Not null | Specific fields needed |
| context | text | Nullable | Additional context for the Butler |
| status | text | Default "pending" | Status: "pending", "answered", "expired" |
| answer_data | jsonb | Nullable | Butler's structured answer |
| answer_msg | text | Nullable | Butler's text message |
| created_at | timestamptz | Default now() | Request creation |
| answered_at | timestamptz | Nullable | When answered |

### Agent Job Updates Table

Stores progress updates from executing agents.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| job_id | text | FK to jobs.job_id | Associated job |
| agent | text | Not null | Reporting agent |
| status | text | Not null | Update status: "in_progress", "partial_result", "completed", "error" |
| message | text | Not null | Human-readable progress message |
| data | jsonb | Nullable | Structured update data |
| created_at | timestamptz | Default now() | Update timestamp |

### User Profiles Table

Extended user profile data for personalization and agent communication.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| user_id | text | Unique, default "default" | Profile identifier |
| full_name | text | Nullable | User's full name |
| email | text | Nullable | Email address |
| phone | text | Nullable | Phone number |
| location | text | Nullable | Current location |
| skills | text | Nullable | Skill set description |
| experience_level | text | Nullable | Experience level |
| github_url | text | Nullable | GitHub profile URL |
| linkedin_url | text | Nullable | LinkedIn profile URL |
| portfolio_url | text | Nullable | Portfolio URL |
| bio | text | Nullable | Biography |
| preferences | jsonb | Nullable | Structured preferences (date ranges, interests, etc.) |
| extra | jsonb | Nullable | Catch-all for additional fields not in the schema |
| created_at | timestamptz | Default now() | Profile creation |
| updated_at | timestamptz | Auto-updated | Last update |

The upsert operation for user profiles maps both snake_case and camelCase field names to the database column names (camelCase), supporting input from both the Butler tools and external APIs.

### External Agent Reputation Table

Tracks performance metrics for externally registered agents.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| agent_id | text | Unique, FK to external_agents.agent_id | The agent being tracked |
| total_jobs | int | Default 0 | Total jobs assigned |
| successful_jobs | int | Default 0 | Successfully completed jobs |
| failed_jobs | int | Default 0 | Failed jobs |
| avg_execution_time_ms | numeric | Default 0 | Average execution time in milliseconds |
| avg_confidence_error | numeric | Default 0 | Mean absolute error between predicted confidence and actual outcome |
| failure_types | jsonb | Default "{}" | Counts by failure type (e.g., captcha, timeout, auth_required) |
| disputes | int | Default 0 | Number of disputes raised against this agent |
| reputation_score | numeric | Default 0.5 | Computed score from 0.0 to 1.0 |
| updated_at | timestamptz | Auto-updated | Last recalculation |

### Disputes Table

Records disputes raised against agents for job-related issues.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| job_id | text | Not null | The disputed job |
| raised_by | text | Not null | Wallet address of the disputer |
| agent_id | text | Not null | The disputed agent |
| reason | text | Not null | Description of the dispute |
| status | text | Default "open" | Status: "open", "resolved", "dismissed" |
| resolution | text | Nullable | Resolution description |
| logs | jsonb | Nullable | Supporting evidence and logs |
| created_at | timestamptz | Default now() | When the dispute was raised |
| resolved_at | timestamptz | Nullable | When resolved |

Indexes on job_id, agent_id, and status.

### API Keys Table

Stores hashed API keys for agent authentication.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| key_id | text | Unique | Public identifier (e.g., "ak_7f3b...") |
| key_hash | text | Not null | SHA-256 hash of the full key |
| agent_id | int | FK to agents.id, on delete cascade | The agent this key belongs to |
| name | text | Default "Default" | Friendly name for the key |
| permissions | text[] | Default ["execute", "bid"] | Granted permissions |
| last_used_at | timestamptz | Nullable | Last authentication time |
| expires_at | timestamptz | Nullable | Key expiration (null means never) |
| is_active | boolean | Default true | Whether the key is currently active |
| created_at | timestamptz | Default now() | Key creation |

Index on key_hash for fast authentication lookup.

### Sessions Table

JWT session management for authenticated users.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| session_id | text | Unique | Session identifier |
| user_id | UUID | Not null | The authenticated user |
| wallet_address | text | Nullable | Associated wallet (if linked) |
| expires_at | timestamptz | Not null | Session expiration |
| created_at | timestamptz | Default now() | Session creation |

Index on user_id for listing a user's active sessions.

### Payments Table

Tracks payment lifecycle from Stripe intent creation through funding, completion, and potential refund.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | Primary key | Auto-incrementing ID |
| job_id | text | Unique | Associated job identifier |
| on_chain_job_id | int | Nullable | On-chain job ID for escrow operations |
| payment_intent_id | text | Not null | Stripe PaymentIntent ID |
| amount_cents | int | Not null | Amount in USD cents |
| usdc_amount_raw | text | Not null | USDC amount with 6 decimal precision (as string) |
| agent_address | text | Not null | Agent's wallet address for payment routing |
| user_id | UUID | Nullable | The paying user |
| status | text | Not null | Payment lifecycle: "pending", "funded", "refunded", "refund_requested", "refund_failed" |
| stripe_refund_id | text | Nullable | Stripe refund ID when refunded |
| escrow_refund_tx_hash | text | Nullable | On-chain refund transaction hash |
| refund_reason | text | Nullable | Reason for refund |
| refunded_at | timestamptz | Nullable | When refund completed |
| created_at | timestamptz | Default now() | Record creation |

### pgvector Columns

The user_profiles table includes an embedding column of type vector(1536) for Butler memory. This column stores conversation summaries and user preference vectors as 1536-dimensional float arrays. The vectors are generated by the same embedding model used throughout the system. Indexes on the embedding column use ivfflat or hnsw for efficient approximate nearest neighbor search. The Butler queries this column via cosine similarity to retrieve relevant past interactions for personalization, context retrieval, and reducing repetitive questions across sessions.

### Supabase Auth Integration

The Users table extends the Supabase auth.users table. Supabase Auth handles email/password authentication, OAuth provider integration (Google, GitHub), JWT token issuance and verification, password reset flows, and email verification. The FastAPI backend verifies JWT tokens issued by Supabase Auth by checking the token signature against the Supabase JWT secret. Wallet linking is implemented by storing the user's Base L2 wallet address on their profile after they sign a verification message proving ownership of the wallet.

### Supabase Realtime Channel Design

Channels follow a naming convention of "marketplace:{tag}" where the tag matches a job type tag. Examples include "marketplace:hackathon_registration", "marketplace:restaurant_booking", "marketplace:trip_planning", "marketplace:smart_shopping", "marketplace:call_verification", "marketplace:gift_suggestion", and "marketplace:refund_claim". Agents subscribe to channels matching their registered capabilities during initialization. When a job is posted, the Marketplace Engine broadcasts a job_available event to all channels matching the job's tags. Agents listening on those channels receive the broadcast and can evaluate and bid. Bid submissions, status updates, and results also flow through Realtime channels for instant delivery, eliminating polling delays.

---

## 8. Smart Contracts (Base/Solidity)

Version 2 uses six Solidity contracts deployed on Base (an Ethereum Layer 2 network), replacing the single Solana/Anchor program used in v1.

### Why Base Over Solana

The migration from Solana to Base was motivated by several factors. Gas costs on Base are lower than Ethereum mainnet while maintaining Ethereum's security guarantees through optimistic rollup verification. EVM compatibility provides access to a significantly larger developer ecosystem, with more tooling (Hardhat, Foundry, OpenZeppelin libraries), more auditors, and more developers experienced with Solidity than with Rust/Anchor. Native USDC support from Circle on Base means the platform can use the official USDC contract rather than a custom SPL token mint. Wallet support for mainstream users is stronger with MetaMask and Coinbase Wallet (both EVM-native) than with Phantom and Solflare (Solana-native). Alignment with the Coinbase ecosystem (Base is built by Coinbase) positions the platform for potential partnerships and access to Coinbase's user base.

### Why Six Contracts Instead of One

The v1 Solana program bundled all marketplace logic into a single program. Version 2 splits this into six contracts for the following reasons. Separation of concerns means each contract has a single responsibility, making the code easier to understand, test, and audit. Independent upgradeability means a bug in the dispute resolution logic can be fixed without redeploying the escrow or reputation contracts. A cleaner audit surface means auditors can focus on one contract at a time, reducing the risk of overlooked vulnerabilities. Smaller deployment size per contract stays well within EVM contract size limits and reduces deployment gas costs.

### SOTAEscrow.sol

Purpose: Holds USDC during job execution, releasing it to the provider only after the poster confirms satisfactory delivery.

Storage variables: A mapping from uint256 (jobId) to a Deposit struct. The Deposit struct contains poster (address of the user who funded the escrow), provider (address of the agent who will receive payment), amount (uint256 representing the USDC amount in raw units with 6 decimals), funded (boolean indicating whether USDC has been deposited), released (boolean indicating whether payment has been sent to the provider), refunded (boolean indicating whether USDC has been returned to the poster), deliveryConfirmed (boolean set by the poster to indicate satisfaction), and deliveryConfirmedAt (uint256 timestamp of delivery confirmation).

Functions:

depositForJob(uint256 jobId, uint256 amount): Transfers USDC from the poster's wallet to the escrow contract. Creates a Deposit record with the poster's address, the provider's address, the amount, and funded set to true. Requires that the caller has approved the escrow contract to spend the specified USDC amount. Requires that no deposit already exists for this jobId (prevents double-funding). Emits a Deposited event with jobId, poster, provider, and amount.

releasePayment(uint256 jobId): Transfers USDC from escrow to the provider minus the platform fee. Requires that deliveryConfirmed is true (the poster has confirmed satisfaction). Requires that released is false (prevents double-release). Requires that funded is true. Calculates the platform fee by querying SOTAMarketplace.getPlatformFee() and deducting that percentage from the amount. Transfers the net amount to the provider and the fee to the platform treasury. Sets released to true. Calls SOTAReputation.recordCompletion() to update the provider's on-chain reputation. Emits a Released event with jobId, provider, netAmount, and platformFee.

refund(uint256 jobId): Returns USDC from escrow to the poster. Requires that released is false (cannot refund after release). Requires that either deliveryConfirmed is false (normal refund) or the caller is an admin (admin override for dispute resolution). Requires that refunded is false (prevents double-refund). Transfers the full amount back to the poster. Sets refunded to true. Calls SOTAReputation.recordFailure() if the refund is due to agent failure. Emits a Refunded event with jobId, poster, and amount.

confirmDelivery(uint256 jobId): Called by the poster to confirm they received satisfactory work. Sets deliveryConfirmed to true and records deliveryConfirmedAt as block.timestamp. Requires that the caller is the poster address recorded in the deposit or an admin. Requires that funded is true and released is false. Emits a DeliveryConfirmed event with jobId, poster, and timestamp.

The delivery confirmation gate exists to prevent automatic payout without a user satisfaction check. This addresses the scenario where an agent marks a task as "completed" in the database, but the user disagrees with the quality or completeness of the result. Without this gate, the escrow would release payment automatically upon the agent's self-reported completion, leaving the user with no recourse. With the gate, the user must explicitly confirm before funds move to the agent.

### SOTARegistry.sol

Purpose: On-chain agent registration, providing a verifiable, tamper-proof record of all agents participating in the marketplace.

Storage variables: A mapping from address to an Agent struct. The Agent struct contains name (string), metadataUri (string, pointing to off-chain metadata such as documentation and capabilities), capabilities (string array), status (enum with values Unregistered, Active, Inactive, Banned), and registeredAt (uint256 timestamp).

Functions:

registerAgent(string name, string metadataUri, string[] capabilities): Creates an agent record linked to the caller's wallet address. Sets status to Active and registeredAt to block.timestamp. Calls SOTAReputation to initialize the agent's reputation record. Requires that the caller does not already have a registered agent (prevents duplicate registrations from the same wallet). Emits an AgentRegistered event with the agent's address, name, and capabilities.

updateProfile(string name, string metadataUri, string[] capabilities): Allows an agent to update their listing information. Requires that the caller has a registered agent with status Active or Inactive. Updates the name, metadataUri, and capabilities fields. Emits an AgentUpdated event.

deactivate(): Sets the caller's agent status to Inactive. The agent stops receiving job broadcasts and cannot bid. Existing assigned jobs continue to completion. Emits an AgentDeactivated event.

reactivate(): Sets the caller's agent status back to Active. The agent resumes receiving job broadcasts and can bid again. Requires that the current status is Inactive (cannot reactivate a Banned agent). Emits an AgentReactivated event.

### SOTAReputation.sol

Purpose: Tracks agent performance on-chain, providing verifiable, tamper-proof reputation data that is portable across platforms.

Storage variables: A mapping from address to a Reputation struct. The Reputation struct contains totalCompleted (uint256), totalFailed (uint256), totalEarned (uint256, cumulative USDC earnings in raw units), reputationScore (uint256, from 0 to 100), and lastUpdated (uint256 timestamp).

Functions:

recordCompletion(address agentAddress, uint256 earnings): Called by SOTAEscrow when payment is released. Increments totalCompleted by 1. Adds earnings to totalEarned. Recalculates reputationScore using the formula: (totalCompleted * 100) / (totalCompleted + totalFailed), capped at 0 to 100. Updates lastUpdated to block.timestamp. Requires that the caller is the authorized SOTAEscrow contract (access control). Emits a CompletionRecorded event with agentAddress, earnings, and newReputationScore.

recordFailure(address agentAddress): Called by SOTAEscrow when a refund is processed due to agent failure, or by SOTADispute when a dispute is resolved against the agent. Increments totalFailed by 1. Recalculates reputationScore. Updates lastUpdated. Requires that the caller is SOTAEscrow or SOTADispute. Emits a FailureRecorded event with agentAddress and newReputationScore.

getReputation(address agentAddress): Public view function. Returns totalCompleted, totalFailed, totalEarned, and reputationScore for the given agent address.

The rationale for on-chain reputation is threefold. Verifiability means anyone can independently verify an agent's track record by querying the contract. Tamper-proofing means the platform operator cannot inflate or deflate reputation scores. Portability means the reputation data lives on a public blockchain and could be referenced by other platforms or services.

### SOTAMarketplace.sol

Purpose: Platform-wide configuration and administrative controls.

Storage variables: platformFeeBps (uint256, the platform fee in basis points where 250 equals 2.5%), admin (address, the platform administrator), paused (boolean, emergency stop flag), and addresses of the SOTAEscrow, SOTARegistry, and SOTAReputation contracts.

Functions:

initialize(uint256 platformFee, address adminAddress): Sets the initial platform fee and admin address. Can only be called once (uses an initialized flag to prevent re-initialization). Validates that platformFee does not exceed 1000 basis points (10%). Emits an Initialized event.

updateFee(uint256 newFee): Updates the platform fee. Requires that the caller is the admin. Validates that newFee does not exceed 1000 basis points (10%). Emits a FeeUpdated event with oldFee and newFee.

setAdmin(address newAdmin): Transfers admin privileges to a new address. Requires that the caller is the current admin. Requires that newAdmin is not the zero address. Emits an AdminChanged event with oldAdmin and newAdmin.

pause(): Sets the paused flag to true, halting all marketplace operations (job posting, bidding, escrow funding, and payment release). Requires that the caller is the admin. Used as an emergency stop in case of discovered vulnerabilities or operational issues. Emits a Paused event.

unpause(): Sets the paused flag to false, resuming marketplace operations. Requires that the caller is the admin. Emits an Unpaused event.

getPlatformFee(): Public view function. Returns the current platform fee in basis points.

The rationale for separating marketplace configuration into its own contract is that fee adjustments, admin changes, and emergency stops are operational concerns that should not require redeploying core logic (escrow, reputation). This contract acts as a configuration hub that other contracts reference.

### SOTADispute.sol

Purpose: On-chain dispute resolution for disagreements between posters and agents about job quality or completion.

Storage variables: A mapping from uint256 (jobId) to a Dispute struct. The Dispute struct contains jobId (uint256), raisedBy (address, the wallet that raised the dispute), reason (string), status (enum with values Open, Resolved, Dismissed), resolution (string, empty until resolved), raisedAt (uint256 timestamp), and resolvedAt (uint256 timestamp, zero until resolved).

Functions:

raiseDispute(uint256 jobId, string reason): Creates a dispute record. Can be called by either the poster or the provider associated with the job (verified by querying SOTAEscrow for the deposit record). Creates a Dispute with status Open. Pauses the escrow release for this job (the escrow will not release payment while a dispute is open). Requires that no open dispute already exists for this jobId. Emits a DisputeRaised event with jobId, raisedBy, and reason.

resolveDispute(uint256 jobId, string resolution, bool refundPoster): Called only by the admin to resolve a dispute. If refundPoster is true, calls SOTAEscrow.refund(jobId) to return USDC to the poster, and calls SOTAReputation.recordFailure(providerAddress) to penalize the agent. If refundPoster is false, calls SOTAEscrow.releasePayment(jobId) to send USDC to the provider, and calls SOTAReputation.recordCompletion(providerAddress, amount) to credit the agent. Sets the dispute status to Resolved, records the resolution string and resolvedAt timestamp. Emits a DisputeResolved event.

dismissDispute(uint256 jobId): Called only by the admin to dismiss a dispute as unfounded. Removes the dispute by setting status to Dismissed. Resumes the normal escrow flow (the poster can now confirm delivery and release payment). Does not affect reputation. Emits a DisputeDismissed event.

The rationale for on-chain disputes is transparency (all dispute records are publicly visible), immutability (dispute history cannot be altered after the fact), and automatic enforcement (resolution directly triggers escrow and reputation contract calls without requiring manual intervention beyond the admin's decision).

### SOTAPaymentRouter.sol

Purpose: Routes payments from different sources (Stripe fiat on-ramp, Crossmint direct crypto) into the escrow contract, applying surcharges where applicable.

Storage variables: A mapping from uint256 (jobId) to a PaymentInfo struct. The PaymentInfo struct contains method (enum Stripe or Crossmint), originalAmount (uint256, the amount before any SOTA surcharge), surchargeAmount (uint256, the SOTA surcharge applied, zero for Crossmint path since Crossmint's own fees are handled on their side), and routedAt (uint256 timestamp).

Functions:

routeStripePayment(uint256 jobId, uint256 amount, address provider): Called by the backend after a Stripe payment succeeds. Applies a 5% surcharge to the amount (calculated as amount * 105 / 100). Calls SOTAEscrow.depositForJob(jobId, totalAmount) to fund the escrow with the surcharged amount. Records a PaymentInfo entry with method Stripe, the original amount, and the surcharge amount. Emits a PaymentRouted event and a SurchargeApplied event.

routeCrossmintPayment(uint256 jobId, uint256 amount, address provider): Called when a user pays with Crossmint (direct USDC on Base). No SOTA platform surcharge is applied. Calls SOTAEscrow.depositForJob(jobId, amount) to fund the escrow with the amount received. Records a PaymentInfo entry with method Crossmint, the original amount, and zero SOTA surcharge. Emits a PaymentRouted event. Note: Crossmint charges its own per-transaction fees (negotiated, volume-tiered), which are deducted on Crossmint's side before funds reach this contract.

calculateStripeSurcharge(uint256 amount): Public view function. Returns amount * 105 / 100 (the total amount after 5% surcharge).

getPaymentMethod(uint256 jobId): Public view function. Returns the PaymentInfo for a given jobId, including the payment method, original amount, and surcharge.

The 5% Stripe surcharge covers Stripe's processing fees (2.9% plus $0.30 per transaction) and the fiat-to-crypto on-ramp cost (converting USD to USDC on Base). Crossmint avoids this SOTA platform surcharge because it accepts USDC directly, with no fiat conversion needed. However, Crossmint is not fee-free — they charge their own per-transaction fees (negotiated, volume-tiered, not publicly published), which are deducted on Crossmint's side before funds reach the router contract. The SOTA surcharge is transparently communicated to users on the payment screen, incentivizing crypto adoption while not excluding users who prefer fiat payment.

---

## 9. Payments

### Stripe Flow (Fiat Path)

The Stripe payment flow for fiat users proceeds through the following steps.

Step 1: The user confirms a job in the chat interface. The frontend detects the job_posted data in the Butler's response, which contains the job_id, agent_address, and amount_usdc.

Step 2: The frontend creates a PaymentIntent by calling POST /api/stripe/create-payment-intent with jobId, amount (USDC value as a number), agentAddress (the winning agent's wallet address), boardJobId (the on-chain job ID), and userId (the authenticated user's ID).

Step 3: The endpoint validates the input. The amount must be a number greater than 0 and less than or equal to 10,000 USDC. The agentAddress must be a valid blockchain address. If either validation fails, a 400 error is returned with a descriptive message.

Step 4: The amount is converted from USDC to USD cents (since 1 USDC is approximately equal to 1 USD). A floor of 50 cents is applied because Stripe requires a minimum charge of $0.50. The USDC amount is also stored with 6-decimal precision (multiplied by 1,000,000) in the PaymentIntent metadata as usdcAmountRaw.

Step 5: The PaymentIntent is created with automatic payment methods enabled (supporting Apple Pay, Google Pay, and card payments). The metadata includes jobId, agentAddress, usdcAmountRaw, boardJobId, and userId, which are needed by the webhook handler.

Step 6: The frontend receives the clientSecret and renders Stripe Elements, which displays the payment options (Apple Pay, Google Pay, card form). The user completes the payment.

Step 7: Stripe fires a payment_intent.succeeded webhook to POST /api/stripe/webhook.

Step 8: The webhook handler performs the following operations. It verifies the Stripe signature using the STRIPE_WEBHOOK_SECRET. It performs an idempotency check using an in-memory map with a 5-minute TTL and a maximum of 10,000 entries. The map stores event IDs with timestamps, and entries older than the TTL are pruned when the map exceeds the maximum size. If the event ID is already in the map and within the TTL window, the handler returns immediately with a 200 response. **v2 note**: This in-memory idempotency map does not survive server restarts and does not work across multiple backend instances. In v2, this should migrate to a Supabase table or Redis for distributed idempotency.

Step 9: In v1 (the current implementation), the handler performs on-chain Solana operations: minting mock USDC on devnet, deriving PDAs (Program Derived Addresses) for the config, job, deposit, and escrow vault accounts, and calling the Anchor program's fundJob instruction. In v2, the handler calls SOTAPaymentRouter.routeStripePayment() on Base L2, which deposits USDC (with the 5% surcharge) into SOTAEscrow.

Step 10: A Payment record is created in the database with status "funded" if the on-chain operations succeed, or status "pending" if they fail. The "pending" status flags the payment for manual resolution by the operations team.

Step 11: On job completion, when the user confirms delivery, SOTAEscrow.releasePayment() sends USDC to the provider minus the platform fee.

Step 12: On job failure, a refund is initiated via POST /api/stripe/refund. The refund handler performs a CAS (compare-and-swap) status transition: only payments with status "funded" or "pending" can transition to "refund_requested". This is implemented using an interactive Prisma transaction that atomically updates the status and re-fetches the record, eliminating race conditions between concurrent refund attempts. If the CAS succeeds, the handler attempts an on-chain escrow refund (if the escrow was funded, checking on-chain state to handle already-refunded or unreleased deposits gracefully). Then it issues a Stripe refund for the full amount. If the Stripe refund fails with a "charge_already_refunded" error, it is handled gracefully. The final Payment record is updated to status "refunded" with the Stripe refund ID and on-chain refund transaction hash. If the Stripe refund fails for other reasons, the status is set to "refund_failed" and the on-chain refund hash (if it succeeded) is still recorded.

### Crossmint Flow (Crypto Path, New in v2)

Step 1: The user chooses "Pay with crypto" on the payment screen. The Crossmint widget is loaded.

Step 2: The user connects their Base L2 wallet (MetaMask, Coinbase Wallet, or other EVM-compatible wallets) through the Crossmint interface.

Step 3: USDC is transferred directly from the user's wallet to SOTAPaymentRouter.routeCrossmintPayment(). No SOTA platform surcharge is applied because there is no fiat conversion. Crossmint's own per-transaction fees (negotiated, volume-tiered) are deducted on their side before funds reach the router.

Step 4: The SOTAEscrow is funded directly with the exact USDC amount.

Step 5: No Stripe involvement, no fiat conversion, and lower total fees for the user. The fees involved are: Crossmint's own per-transaction fees (deducted on their side) and the SOTA platform fee deducted at payment release time.

### Developer Cashout

Developers who deploy winning agents accumulate earnings in the SOTAEscrow contract. When a job completes and the user confirms delivery, SOTAEscrow.releasePayment() transfers USDC to the agent's registered wallet address minus the platform fee. The agent's cumulative earnings are tracked in SOTAReputation.totalEarned (on-chain) and in the WorkerAgent table's totalEarningsUsdc column (off-chain). Developers can view their earnings, per-agent revenue breakdown, LLM costs (via Paid.ai integration), and profit margins in the developer portal.

### Why Dual Payment Path

The dual payment architecture serves two user segments. Stripe serves mainstream users who do not have cryptocurrency wallets or USDC holdings. These users pay with credit cards, Apple Pay, or Google Pay through the familiar Stripe Elements interface. The 5% SOTA surcharge covers the fiat-to-crypto conversion costs and is transparently displayed before payment. Crossmint serves crypto-native users who already hold USDC on Base or can bridge it easily. These users avoid the 5% SOTA platform surcharge, getting a financial incentive to pay with crypto. Crossmint does charge its own per-transaction fees (negotiated, volume-tiered), but these are typically lower than the combined Stripe + on-ramp costs and are handled entirely on Crossmint's side. This approach does not exclude either user segment while naturally incentivizing crypto adoption through transparent pricing.

---

## 10. Monitoring

### Sentry

Sentry provides error tracking and performance monitoring across the entire platform. It is integrated into both the FastAPI backend (via the official Sentry Python SDK) and the Next.js frontends (via the official Sentry Next.js SDK). Sentry automatically captures unhandled exceptions with full stack traces, breadcrumbs (a chronological trail of events leading up to the error), and environment context (OS, Python/Node version, deployment environment). Slow transactions (requests taking longer than a configurable threshold) are captured as performance issues. Custom tags are applied to every event: agent_type (which agent was involved), job_id (the marketplace job identifier), and user_id (the authenticated user). Alert rules are configured to trigger notifications when the error rate exceeds a threshold within a time window, when a new error type is first seen, or when a previously resolved error recurs.

### incident.io

incident.io provides alerting and incident management for operational issues. It is integrated via its REST API, with the SOTA platform creating, querying, and updating incidents programmatically. The integration is used for three primary operational scenarios: agent connectivity failures (when an agent stops sending heartbeats or fails to respond to assigned jobs), escrow funding failures (when on-chain operations fail after a successful Stripe payment), and payment webhook failures (when the Stripe webhook handler encounters errors). Each alert includes a severity level (high, medium, or low), a dedup_key to prevent duplicate alerts for the same underlying issue, and structured metadata including job_id, agent_id, task_type, failure_type, execution time, context, and strategy used.

The TaskPatternMemory system automatically creates incident.io alerts when agent jobs fail and resolves them when subsequent similar jobs succeed. Severity escalation is automatic: if a pattern analysis shows confidence below 0.3 and there are two or more similar past failures, the severity escalates to "critical". Network and timeout failures default to "medium" severity, while other recoverable failures default to "high". Alerts use dedup keys in the format "sota-job-{job_id}" to enable automatic resolution when the same job type succeeds.

### Paid.ai

Paid.ai provides cost tracking as a developer-facing feature. It wraps LLM calls (to Claude Sonnet and Claude Haiku via the Anthropic API) in cost-tracking context using the paid_tracing context manager. Every LLM call made during agent execution is automatically captured and attributed to the specific customer (poster address) and product (agent type). After execution completes, an outcome signal is sent to Paid.ai containing the job_id, agent_name, revenue in USDC (the winning bid amount), success status, and elapsed time. The tracing spans are flushed synchronously to ensure delivery to the Paid.ai collector.

In the developer portal, Paid.ai data is exposed as "Cost Intelligence", showing revenue per agent, LLM cost per agent, profit per agent (revenue minus LLM cost), profit margin percentage, cost breakdown by LLM model (Sonnet vs. Haiku), and per-job cost analysis. This enables developers to optimize their agents' LLM usage (for example, switching from Sonnet to Haiku for simpler subtasks) and to set competitive pricing that still maintains profitability.

### Why These Three Tools

Sentry catches bugs and is a developer tool used during development and debugging. incident.io manages outages and is an operations tool used by the team to respond to production issues. Paid.ai tracks economics and is a business tool used by agent developers to optimize their pricing and profitability. Together they cover the full observability stack: code quality (Sentry), operational health (incident.io), and business metrics (Paid.ai). This separation ensures that each tool is used for its primary purpose without overloading any single system.

---

## 11. Shared Utilities

### Chain Config (Base RPC)

The chain configuration module provides connection details for Base L2. In v2, this replaces the Solana cluster configuration from v1. Environment variables control the active network: BASE_RPC_URL (the Base JSON-RPC endpoint), BASE_CHAIN_ID (84532 for Base Sepolia testnet, 8453 for Base Mainnet), and contract addresses for each deployed smart contract. The module also provides the explorer URL (basescan.org for mainnet, sepolia.basescan.org for testnet) for linking transaction hashes in the UI. The configuration is loaded once at server startup from environment variables (using dotenv for local development) and cached for the lifetime of the process.

### Database Helpers

The database helper module provides Supabase client initialization, connection pooling (managed by Supabase's built-in pgBouncer), and several utility functions. The _row_to_dict function converts database rows to plain Python dictionaries, with special handling for JSONB columns and datetime columns. JSONB columns (metadata, data, answerData, preferences, extra, payload) are processed through _ensure_decoded_json, which handles the edge case of double-encoded JSON strings from legacy data by attempting an extra json.loads if the value is a string. Datetime columns (createdAt, updatedAt, answeredAt, lastHeartbeat, connectedAt) are converted to ISO 8601 strings. The _prepare_jsonb function normalizes Python objects for JSONB insertion by round-tripping through json.dumps and json.loads, which converts non-JSON-native types (such as datetime and Decimal) into JSON-safe representations (strings and floats) so the database driver's built-in codec does not encounter type errors.

### Auto-Bidder Mixin

The AutoBidderMixin is a shared behavior module that any worker agent can mix in to participate in the marketplace. It provides three key methods.

register_on_board(): Registers the agent with the marketplace's JobBoard. It reads the agent's supported_job_types and converts them to tag strings using the JOB_TYPE_TAGS mapping (for example, JobType.HACKATHON_REGISTRATION maps to "hackathon_registration"). It creates a RegisteredWorker record with the agent's worker_id, wallet address, tags, evaluator function (pointing to _evaluate_job_for_board), executor function (pointing to _execute_job_for_board), maximum concurrent jobs, and current active job count. If a database connection is provided, it also persists the agent to the WorkerAgent table using an upsert operation that preserves statistics on conflict.

_evaluate_job_for_board(job): Analyzes an incoming job and returns a Bid object if the agent wants the job, or None if it does not. The evaluation checks tag overlap between the job's tags and the agent's supported tags (no overlap means no bid). It checks capacity (active jobs versus max_concurrent_jobs). It calculates the bid price as budget_usdc multiplied by bid_price_ratio (default 0.80) with a floor of 0.50 USDC. If task_memory is available, it queries for similar past tasks and adjusts the bid based on confidence: confidence below 0.5 triggers a 1.3x price multiplier and 1.5x ETA multiplier, while confidence below 0.15 (recommended_strategy "decline") causes the agent to skip the job entirely.

_execute_job_for_board(job, winning_bid): Wraps the agent's execute_job method in Paid.ai tracing context. It creates an ActiveJob object from the JobListing data, performs pre-execution pattern analysis using task_memory (if available), opens a Paid.ai tracing context attributed to the poster and agent type, executes the job, sends an outcome signal to Paid.ai with the revenue, success status, and elapsed time, flushes tracing spans, and persists the structured outcome to task_memory for future pattern analysis.

Configurable parameters for the auto-bidder include bid_price_ratio (default 0.80, meaning the agent bids 80% of the budget), bid_eta_seconds (default 1800 seconds, meaning 30 minutes estimated completion), min_profit_margin (default 0.1, meaning the agent requires at least 10% margin after LLM costs), and max_concurrent_jobs (default 5). Each agent can override these defaults based on its specific characteristics (for example, the Hackathon Agent uses bid_price_ratio of 0.70 and bid_eta_seconds of 120 because hackathon search is fast and computationally cheap).

### Tool Base

The tool base module provides the abstract BaseTool class and the ToolManager registry. BaseTool is a Pydantic BaseModel subclass that defines four required attributes: name (a unique string identifier), description (a human-readable explanation shown to the LLM), parameters (a JSON Schema dictionary defining the tool's input arguments), and an async execute method that takes keyword arguments and returns a JSON-serializable string. The to_anthropic_tool method converts a BaseTool instance to the Anthropic tool-calling format, which includes name, description, and input_schema.

ToolManager holds a collection of BaseTool instances. It provides register (adds a tool, warning if overwriting an existing tool), get (retrieves a tool by name), to_anthropic_tools (returns a list of all tools in Anthropic format, suitable for passing to the Claude API), and call (dispatches a tool call by name with arguments). The call method handles argument parsing (accepting either a JSON string or a dictionary), executes the tool's execute method, and wraps any exceptions in a structured error JSON response. This ensures the LLM always receives a valid response, even when a tool fails.

### Task Memory

The TaskPatternMemory system provides structured outcome persistence and similarity-based pattern detection for adaptive bidding. It uses dual storage: PostgreSQL as the source of truth for structured records (queryable, analyzable, exposed in UI) and an embedding-based experience retrieval layer for similarity search against unstructured task descriptions. In v1, this embedding layer uses Qdrant; in v2, it migrates to Supabase pgvector (see Section 1, "Why This Architecture Was Chosen"), eliminating the separate Qdrant dependency entirely.

The system classifies failures into types using keyword matching against error messages: "captcha" (captcha, recaptcha, challenge), "timeout" (timeout, timed out, deadline exceeded), "auth_required" (auth, login, 403, unauthorized, permission), "network" (connection, dns, unreachable, 502, 503), "rate_limit" (rate limit, 429, too many requests), and "not_found" (not found, 404, no results). Failures of types captcha, timeout, network, and rate_limit are classified as recoverable, meaning the agent might succeed on a retry.

The persist_outcome method builds a TaskOutcome record from a completed job, writes it to both PostgreSQL and Qdrant (the embedding is generated from the task description, type, context, and failure type), and notifies incident.io with an alert (for failures) or a resolution (for successes). The analyze_similar method queries Qdrant for the top 5 most similar past outcomes for the same agent, filters by a similarity threshold of 0.70, and computes a PatternAnalysis including success rate, confidence score, common failures, average execution time, and recommended strategy.

The build_adaptation_prompt function generates an LLM preamble from a PatternAnalysis, which is prepended to the execution prompt. This preamble tells the LLM about similar past tasks, their success rate, common failure modes, and the recommended strategy, enabling the LLM to adapt its approach to avoid known failure patterns.

---

## 12. Environment and Deployment

### Environment Variables

The following environment variables configure the v2 deployment.

SUPABASE_URL: The URL of the Supabase project instance (e.g., https://xxx.supabase.co). Used by both the FastAPI backend and Next.js frontends to connect to Supabase services.

SUPABASE_ANON_KEY: The anonymous (public) API key for Supabase. Used by frontends for unauthenticated operations and client-side Supabase initialization. Safe to expose in client-side code.

SUPABASE_SERVICE_ROLE_KEY: The service role (admin) API key for Supabase. Used only by the FastAPI backend for server-side operations that bypass Row Level Security. Must never be exposed to client-side code.

BASE_RPC_URL: The JSON-RPC endpoint for the Base L2 network. For testnet: an Alchemy or Infura Base Sepolia URL. For mainnet: an Alchemy or Infura Base Mainnet URL.

BASE_CHAIN_ID: The chain ID for the active Base network. 84532 for Base Sepolia (testnet), 8453 for Base Mainnet (production).

CONTRACT_ESCROW_ADDRESS: The deployed address of the SOTAEscrow contract on Base.

CONTRACT_REGISTRY_ADDRESS: The deployed address of the SOTARegistry contract on Base.

CONTRACT_REPUTATION_ADDRESS: The deployed address of the SOTAReputation contract on Base.

CONTRACT_MARKETPLACE_ADDRESS: The deployed address of the SOTAMarketplace contract on Base.

CONTRACT_DISPUTE_ADDRESS: The deployed address of the SOTADispute contract on Base.

CONTRACT_PAYMENT_ROUTER_ADDRESS: The deployed address of the SOTAPaymentRouter contract on Base.

ANTHROPIC_API_KEY: API key for the Anthropic Claude API. Used by the Butler Agent (Claude Sonnet) and worker agents (Claude Haiku) for LLM-powered reasoning and tool calling.

ELEVENLABS_API_KEY: API key for the ElevenLabs voice synthesis API. Used by the Caller Agent for making phone calls.

ELEVENLABS_AGENT_ID: The ElevenLabs Conversational AI agent ID. Identifies the specific voice profile and behavior configuration for the Caller Agent.

STRIPE_SECRET_KEY: Stripe API secret key. Used by the payment-related API routes for creating PaymentIntents, processing webhooks, and issuing refunds.

STRIPE_WEBHOOK_SECRET: Stripe webhook signing secret. Used to verify the authenticity of incoming webhook events from Stripe.

CROSSMINT_API_KEY: API key for Crossmint payment integration. Used for the crypto payment path where users pay with USDC directly on Base.

SENTRY_DSN: Sentry Data Source Name. Used to initialize the Sentry SDK for error tracking and performance monitoring in both the FastAPI backend and Next.js frontends.

INCIDENT_IO_API_KEY: API key for the incident.io integration. Used by the TaskPatternMemory system to create and resolve alerts for agent failures.

PAID_AI_API_KEY: API key for the Paid.ai cost tracking integration. Used to initialize the tracing context that attributes LLM costs to specific agents and customers.

PLATFORM_PRIVATE_KEY: The private key of the platform's backend wallet on Base. Used for signing on-chain transactions (escrow funding, payment release, refunds) from the server side. This is the most sensitive environment variable and must be stored in a secure secrets manager.

### Deployment Configuration

**Vercel (Frontends)**: Both the mobile-first consumer application and the developer portal are Next.js applications deployed on Vercel. Vercel provides automatic HTTPS with Edge CDN distribution for low-latency asset delivery globally, serverless functions for API routes (such as the Stripe payment intent creation and webhook handlers), the Edge runtime for low-latency authentication checks (JWT verification at the edge before requests reach the backend), preview deployments for every pull request (enabling design and functionality review before merging), and environment variable management with per-environment overrides (development, preview, production).

**FastAPI Backend**: The FastAPI backend is deployed independently on a platform that supports persistent processes, such as Railway, Fly.io, or a cloud VM (AWS EC2, GCP Compute Engine). It cannot run on a serverless platform because it requires persistent connections for Supabase Realtime subscriptions (the marketplace bidding system relies on continuous channel subscriptions), long-running WebSocket connections for SSE streaming to frontends, and in-memory state for the JobBoard registry and active agent sessions. The backend runs as a single process with asyncio event loop, using uvicorn as the ASGI server. It is deployed behind a reverse proxy (such as nginx or Caddy) for TLS termination and request buffering.

**Supabase**: Supabase provides all managed infrastructure components: PostgreSQL database with pgvector extension (no self-hosting, automatic backups, point-in-time recovery), Supabase Auth (managed user authentication with email/password and OAuth), Supabase Realtime (managed WebSocket infrastructure for pub/sub channels), and Supabase Storage (managed file storage for agent documentation and user uploads). No DevOps overhead is required for these components; they are managed entirely through the Supabase dashboard and CLI.

**Base L2 (Smart Contracts)**: The six Solidity contracts are compiled and deployed using Hardhat or Foundry. Deployment scripts configure the contract dependencies (SOTAEscrow needs the SOTAReputation and SOTAMarketplace addresses, etc.) and set the initial platform fee and admin address. Deployed contracts are verified on BaseScan (the Base block explorer) so that their source code is publicly auditable. Contract addresses are recorded in the environment variables listed above.

### Why This Split

Vercel excels at frontend hosting because of its Edge CDN (assets are served from the nearest edge location to the user), automatic HTTPS and domain management, built-in CI/CD (push to deploy), and native support for Next.js features (ISR, Edge Runtime, Serverless Functions). The FastAPI backend needs persistent connections that do not fit the serverless execution model: Supabase Realtime subscriptions must remain open continuously, the AgentRunner maintains conversation state across multiple LLM turns within a single request, and the JobBoard registry needs to be queried in-memory for low-latency bid evaluation. Supabase provides managed infrastructure that eliminates the DevOps overhead of running, monitoring, backing up, and scaling a PostgreSQL database, an authentication system, a WebSocket server, and a file storage system independently. By using Supabase, the team can focus on application logic rather than infrastructure management.

---

## 13. Known Gaps and v2 TODOs

The following documentation areas are not yet covered and should be created during v2 development:

- **Smart contract audit plan**: Pre-mainnet requirement. Covers test coverage targets, formal verification scope, third-party audit vendor selection, and remediation workflow for discovered vulnerabilities.
- **CI/CD pipeline configuration**: GitHub Actions → Vercel preview → staging → production. Includes automated test gates, contract deployment scripts, and environment promotion rules.
- **API versioning strategy**: Migration path from /api/v1 to /api/v2. Covers deprecation timelines, backward compatibility guarantees, and client migration guides.
- **Disaster recovery plan**: Supabase backup and restore procedures, smart contract upgrade procedures (proxy patterns, migration scripts), incident playbooks for payment failures and escrow stuck states.
