# SOTA Mobile Backend Technical Documentation (v2)

## 1. Architecture

The mobile app's backend is split between two systems. The shared FastAPI server handles all core marketplace and Butler operations (chat, job creation, bidding, execution). The mobile app itself hosts lightweight Next.js API routes for concerns specific to the mobile experience: authentication, chat persistence, ElevenLabs token management, and payment processing.

This split exists because the FastAPI server is the single source of truth for marketplace state, while the mobile app needs local routes for operations that must run close to the client (Stripe webhooks, auth session cookies) or that require server-side secrets (ElevenLabs API key, Stripe secret key).

In v2, the mobile app connects directly to Supabase for auth (replacing custom JWT) and real-time updates (replacing WebSocket polling). The FastAPI server remains the backend for Butler AI interactions, job lifecycle management, and on-chain operations.

Deployment: The mobile Next.js app is deployed on Vercel. The FastAPI server runs on a separate persistent host. Supabase is managed and shared between both.

## 2. Shared FastAPI Integration

The mobile app calls the shared FastAPI backend for all Butler and marketplace operations. The base URL is configured via NEXT_PUBLIC_BUTLER_API_URL (default: http://localhost:3001/api/v1).

**POST /api/v1/chat**: The primary Butler interaction endpoint. The mobile app sends the user's message (query string + timestamp). The FastAPI server processes it through the Claude-backed Butler agent, which may invoke tools (fill_slots, post_job, check_agent_requests, etc.). The response includes the Butler's text response and optionally a job_posted object if a marketplace job was created. The mobile app renders the response in the chat transcript and, if job_posted is present, triggers the payment flow.

**POST /api/v1/create**: Create and fund a job on-chain. Called internally by the Butler when the user confirms a task. The mobile app doesn't call this directly — it's triggered by the Butler's post_job tool. Returns the on-chain job ID, escrow details, and winning bid information.

**POST /api/v1/status**: Check job status and delivery confirmation. The mobile app can poll this to show execution progress. Returns current job status (open, bidding, assigned, executing, completed, failed), delivery confirmation state, and any result data.

**GET /api/v1/marketplace/jobs**: List current marketplace jobs. The mobile app uses this to show the marketplace view and for the get_job_listings client tool (accessible via voice). Returns an array of jobs with job_id, description, status, budget_usdc, tags, bid count.

**GET /api/v1/marketplace/bids/{job_id}**: Get bids for a specific job. Used in the marketplace view to show bidding activity.

**POST /api/v1/marketplace/post**: Post a new job to the marketplace. The mobile app calls this when a JSON job payload is extracted from the voice agent's output or when the user explicitly posts from the chat. The payload includes task description, tool type, parameters, wallet address, and budget. The endpoint broadcasts the job to matching agents via Supabase Realtime, waits for the bid window (15 seconds default), selects the winner, and returns the result with escrow information.

**POST /api/v1/marketplace/execute/{job_id}**: Trigger execution of an assigned job. Called after payment is confirmed. The winning agent executes the task and returns formatted results. The mobile app renders these results in the chat transcript.

**Job creation from voice chat**: When the user speaks a task request, the ElevenLabs voice agent processes it through the Butler, which fills slots (gathering required parameters via conversation), asks for confirmation, and then calls post_job. The mobile app's interceptJsonJob function also scans assistant messages for JSON objects containing a "task" field, automatically posting them to the marketplace. This dual-path ensures jobs are created whether the Butler uses tools explicitly or outputs structured JSON.

## 3. Mobile API Routes (Next.js)

These routes run within the mobile Next.js application and handle concerns that require proximity to the client or server-side secrets.

### /api/chat

**POST**: Saves a chat message to the database. Requires sessionId (UUID), role (user/assistant/system), and text. Optionally accepts wallet (wallet address) and userId (integer user ID). The handler upserts the chat session — if the session does not exist, it creates one with the provided wallet and userId; if it exists, it updates the updatedAt timestamp. The first user message in a session becomes the title (truncated to 80 characters). A race condition is handled: if an assistant message creates the session first (title would be null), the next user message's candidateTitle overwrites it. After upserting the session, a ChatMessage record is created and returned with status 201. Error handling: returns 400 if required fields are missing, 500 on database error.

**GET**: Loads chat data with three query modes. If sessionId is provided, returns all messages for that session ordered by createdAt ascending. If userId is provided (must be a valid integer), returns up to 50 chat sessions for that user ordered by updatedAt descending. If wallet address is provided, returns up to 50 sessions for that wallet. If no filter is provided, returns the 20 most recent sessions. Error handling: returns 400 if userId is not a valid integer, 500 on database error.

### /api/elevenlabs/token

**GET**: Fetches a one-time conversation token from ElevenLabs. The endpoint protects the ELEVENLABS_API_KEY by keeping it server-side and only exposing ephemeral tokens to the client.

Rate limiting: In-memory sliding window rate limiter. Tracks timestamps per IP address (extracted from x-forwarded-for header, falls back to "unknown"). Maximum 10 requests per 60-second window. Returns 429 Too Many Requests if exceeded. **v2 note**: This in-memory rate limiter does not survive server restarts and does not work across multiple backend instances. In v2, this should migrate to Redis or a Supabase-backed sliding window for distributed rate limiting.

Token generation: Calls the ElevenLabs API at /v1/convai/conversation/token with the agent ID as a query parameter and the API key in the xi-api-key header. Validates the response contains a non-empty string token. Returns the token as JSON.

Error handling: Returns 500 if ELEVENLABS_AGENT_ID or ELEVENLABS_API_KEY environment variables are missing. Returns 502 if the ElevenLabs API returns a non-OK response or an invalid token format.

### /api/auth/login

**POST**: Authenticates a user with email and password. Validates that both email and password are non-empty strings. Looks up the user by lowercase email. Verifies the password against the stored hash using the verifyPassword helper. On success, creates a JWT session token via createSessionToken and returns the user object (id, email, name) and token. On failure, returns 401 with "Invalid email or password" (intentionally vague to prevent enumeration). Returns 400 for invalid input, 500 for server errors.

### /api/auth/register

**POST**: Creates a new user account. Validates: email must be a string containing "@", password must be between 6 and 1024 characters. Checks for existing user with same lowercase email (returns 409 if found). Creates user record with hashed password and optional name. Generates JWT session token. Returns user object and token with status 201. The password length upper bound (1024) prevents denial-of-service via extremely long passwords that would be expensive to hash.

### /api/auth/me

**GET**: Returns the currently authenticated user. Requires Authorization header with Bearer token. Extracts and verifies the JWT via verifySessionToken. Looks up the user by ID from the token payload. Returns 401 if no auth header, invalid token, or user not found. Returns user object (id, email, name) on success.

### /api/stripe/create-payment-intent

**POST**: Creates a Stripe PaymentIntent for job escrow funding. Validates: jobId or boardJobId must be present, agentAddress must be a valid address (in v1: Solana base58; in v2: Ethereum hex address), amount must be a number between 0 and 10,000. Converts USDC amount to USD cents at 1:1 ratio, enforcing Stripe's minimum of $0.50 (50 cents). Creates the PaymentIntent with automatic_payment_methods enabled (supports Apple Pay, Google Pay, card) and metadata containing jobId, agentAddress, usdcAmountRaw (amount * 10^6 for 6 decimal USDC precision), boardJobId, and userId. Returns the client_secret for the frontend to complete payment.

### /api/stripe/webhook

**POST**: Handles Stripe payment events (primarily payment_intent.succeeded). Verifies the webhook signature using STRIPE_WEBHOOK_SECRET. Returns 400 if signature is missing or invalid.

Idempotency: Maintains an in-memory Map of processed event IDs with timestamps. Events are skipped if already processed within a 5-minute TTL window. The map is pruned when it exceeds 10,000 entries by removing entries older than 5 minutes. **v2 note**: This in-memory idempotency map does not survive server restarts and does not work across multiple backend instances. In v2, this should migrate to a Supabase table or Redis for distributed idempotency.

On payment_intent.succeeded: Extracts metadata (jobId, agentAddress, usdcAmountRaw, boardJobId, userId). In v1: loads Solana platform keypair, mints mock USDC to platform wallet (devnet faucet), derives Anchor program PDAs, calls fundJob to lock USDC in on-chain escrow. In v2: calls SOTAPaymentRouter.routeStripePayment() on Base to deposit USDC with 5% surcharge into SOTAEscrow. Creates Payment database record with status "funded".

If on-chain operations fail: Still creates Payment record with status "pending" for manual resolution. This ensures the Stripe charge is tracked even if blockchain operations encounter issues.

### /api/stripe/refund

**POST**: Processes refunds for failed jobs. Authenticated via x-internal-api-key header (shared secret between services). Validates job_id is present. Looks up Payment record by jobId.

Idempotency: Returns success if already refunded (with existing refund IDs). Returns 409 if refund is already in progress (status "refund_requested").

Atomic status transition: Uses a Prisma interactive transaction for compare-and-swap. Atomically checks that status is "funded" or "pending" and updates to "refund_requested". If the CAS fails (status was already changed by another request), returns 409.

On-chain refund (step 1): If the payment was in "funded" status and has an on-chain job ID, attempts on-chain escrow refund. In v1: derives Solana PDAs, checks deposit account state (skips if already refunded, not funded, or already released), calls the Anchor program's refund instruction. In v2: calls SOTAEscrow.refund() on Base. Continues to Stripe refund even if on-chain refund fails (user getting their card money back is the priority).

Stripe refund (step 2): Creates a Stripe refund for the full PaymentIntent amount. Handles already-refunded charges gracefully (sets stripeRefundId to "already_refunded"). If Stripe refund fails: updates Payment status to "refund_failed" with partial results (escrow refund tx hash if it succeeded) and returns 500.

Final update (step 3): Updates Payment record to "refunded" with stripeRefundId, escrowRefundTxHash, refundReason, and refundedAt timestamp.

### /api/crossmint/* (v2 — new)

New endpoints for Crossmint crypto payments. Will handle: creating Crossmint payment sessions, receiving Crossmint webhooks when USDC transfer completes on Base, and calling SOTAPaymentRouter.routeCrossmintPayment() to fund escrow without the 5% SOTA platform surcharge. Note: Crossmint charges its own per-transaction fees (negotiated, volume-tiered), which are deducted on Crossmint's side before funds arrive at the router.

## 4. ElevenLabs Voice Backend

**Token generation**: The ElevenLabs API key is a server-side secret. The mobile app's /api/elevenlabs/token endpoint acts as a secure proxy, generating one-time conversation tokens. The token is used by the client to establish a WebRTC connection with ElevenLabs' servers.

**Rate limiting**: The in-memory rate limiter uses a sliding window of 60 seconds with a maximum of 10 requests per IP. Timestamps are stored in arrays per IP key. On each request, expired timestamps are filtered out before checking the count. This prevents abuse while allowing legitimate reconnection scenarios (user's voice session drops and they need a new token).

**Conversation session lifecycle**: The client starts a session by fetching a token, then calling conversation.startSession with the token and WebRTC connection type. The session remains active until explicitly ended (user taps orb) or the connection drops (network issue, tab closure). On disconnect, the client can request a new token and start a fresh session.

**Agent ID configuration**: Set via ELEVENLABS_AGENT_ID environment variable. This identifies the specific ElevenLabs Conversational AI agent that powers the Butler voice interface. The agent is configured in the ElevenLabs dashboard with: system prompt, voice settings, client tools (post_job, query_butler, get_job_listings), and response behavior.

## 5. Payment Processing

**Stripe PaymentIntent creation**: The create-payment-intent endpoint is the entry point for all Stripe payments. Amount validation ensures no zero-dollar or excessively large charges. The conversion from USDC to cents assumes 1 USDC equals 1 USD, which is a reasonable approximation for a stablecoin. The minimum of $0.50 is Stripe's hard minimum for PaymentIntents.

**Payment metadata**: Critical for the webhook handler to process the payment correctly. jobId links to the marketplace job. agentAddress identifies where on-chain payment should go. usdcAmountRaw stores the precise USDC amount in 6-decimal integer format (e.g., 1.50 USDC = "1500000"). boardJobId links to the on-chain job ID for escrow funding. userId associates the payment with a user account.

**Payment method routing (v2)**: Users choose between Stripe (fiat) and Crossmint (crypto) at the payment step. Stripe path adds a transparent 5% SOTA surcharge displayed to the user before they confirm. Crossmint path transfers USDC directly on Base with no SOTA platform surcharge (Crossmint's own negotiated per-transaction fees are deducted on their side before funds arrive). Both paths ultimately fund the same SOTAEscrow contract, just through different routes in SOTAPaymentRouter.

**Refund logic**: The refund endpoint implements a careful multi-step process with idempotency and partial failure handling. The CAS (compare-and-swap) pattern prevents double refunds in concurrent scenarios. The on-chain refund is attempted first, but if it fails, the Stripe refund still proceeds — the principle being that returning money to the user's card takes priority over blockchain state consistency, which can be reconciled manually.

**Payment state machine**: pending (Stripe succeeded but on-chain failed) -> funded (both Stripe and on-chain succeeded) -> refund_requested (CAS locked for refund) -> refunded (both refunds completed) or refund_failed (partial failure). Each transition is atomic and idempotent.

## 6. Auth Flow

**v1 (current — custom JWT)**: User registers with email/password, password hashed, JWT issued with userId payload. Login verifies password hash, issues JWT. /api/auth/me verifies JWT and returns user. Tokens have no explicit expiry in the current implementation — this is a **known v1 security gap**. In v2, Supabase Auth issues short-lived access tokens (1 hour default) with automatic refresh tokens, eliminating this vulnerability.

**v2 (planned — Supabase Auth)**: Supabase Auth handles registration, login, OAuth (Google, GitHub), and session management. The mobile app uses Supabase's client library for auth operations. JWT tokens are issued by Supabase with built-in expiry and refresh. The app stores the session in cookies or localStorage via Supabase's session persistence.

**Wallet address linking**: In v2, users can link their Base wallet address to their Supabase profile. This allows associating on-chain activity (escrow deposits, earnings) with the user account. Linking is done after auth: user signs a message with their wallet, backend verifies the signature, and stores the wallet address on the user's profile.

**Session cookies**: In v2, Supabase handles session cookies automatically. The mobile app sends the access token with each API request. The FastAPI backend verifies the Supabase JWT using the Supabase JWKS endpoint.

## 7. Data Flow

End-to-end flow from voice input to result delivery:

**Step 1 — Voice Input**: User taps the ButlerSphere orb. The mobile app fetches an ElevenLabs conversation token from /api/elevenlabs/token (rate limited, server-side API key). The client establishes a WebRTC session with ElevenLabs using the token. User speaks their request. ElevenLabs transcribes the speech and processes it through the configured AI agent.

**Step 2 — Butler Processing**: The ElevenLabs agent invokes the query_butler client tool, which POSTs the transcribed text to the FastAPI backend at /api/v1/chat. The Butler agent (Claude-powered) interprets the request. If the task requires marketplace action, the Butler calls fill_slots to gather structured parameters through conversation with the user. Once all slots are filled, the Butler asks for confirmation.

**Step 3 — Job Posting**: On confirmation, the Butler calls post_job, which creates a marketplace job with description, tags, budget, and parameters. The job is broadcast to matching agents via Supabase Realtime channels.

**Step 4 — Bidding**: Matching agents (subscribed to relevant Realtime channels) receive the job and evaluate it. Agents with matching capabilities submit bids (amount_usdc, estimated_seconds) within the bid window (15 seconds default). The mobile app shows a BidProgressBar animation during this phase.

**Step 5 — Winner Selection**: After the bid window closes, the marketplace engine selects the winner (lowest price, earliest submission as tiebreaker). The winning agent receives bid_accepted, losers receive bid_rejected. The result is returned to the mobile app, which displays the winning bid details.

**Step 6 — Payment**: If the job requires escrow funding (indicated by escrow.needs_user_funding in the response), the mobile app triggers the payment UI. The StripePayment component creates a PaymentIntent and shows Apple Pay / Google Pay / card input. Alternatively, the user can choose Crossmint for direct USDC payment on Base (v2). On payment success, the webhook handler funds the on-chain escrow.

**Step 7 — Execution**: After payment confirmation, the mobile app POSTs to /api/v1/marketplace/execute/{job_id}. The winning agent executes the task (web scraping, API calls, LLM processing, etc.). The TaskExecutionProgress component shows animated dots during execution.

**Step 8 — Result Delivery**: The agent returns formatted results, which the mobile app renders in the chat transcript as a Butler message. The user can see the results, ask follow-up questions, or start a new task. The job status on-chain transitions to completed, and the provider can claim their escrow payout via delivery confirmation.

**Failure path**: If no bids are received, the job expires and the Butler informs the user ("No specialists available, would you like to try again?"). If the winning agent fails, the job is marked as failed, and the refund process is triggered (on-chain escrow refund + Stripe refund). If payment fails, the user is shown an error and can retry or switch payment methods.
