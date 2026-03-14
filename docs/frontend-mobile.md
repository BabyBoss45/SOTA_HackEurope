# SOTA Mobile Frontend Technical Documentation (v2)

## 1. Architecture

The mobile frontend is a Next.js 15 application using React 19, TypeScript, and Tailwind CSS. It serves as both a progressive web app for mobile browsers and can be wrapped for iOS via Capacitor or similar. It is a separate project from the developer portal/landing page, with its own deployment on Vercel.

In v2, the frontend connects to a shared FastAPI backend for Butler interactions and marketplace operations, and directly to Supabase for auth, chat persistence, and real-time updates. The wallet layer changes from Solana (Phantom, WalletConnect) to Base/Ethereum (MetaMask, Coinbase Wallet, WalletConnect v2).

Key architectural decisions: Next.js 15 App Router for file-based routing and server components. React 19 for concurrent features. Tailwind CSS for utility-first styling with CSS custom properties for theming. React Query (TanStack Query) for server state management with 60-second stale time. Framer Motion for animations.

## 2. Pages and Routes

The mobile app has a minimal route structure optimized for the primary use case: talking to Butler and paying for tasks.

Main app shell: Root layout provides providers (auth, wallet, query client), global styles, font loading. The shell includes a header with app title and navigation.

Chat page (main route "/"): The primary interface. Shows the ButlerSphere orb at the bottom, transcript area above, text input bar. Users can speak (via orb) or type. Handles job posting, bid visualization, payment flow all within the chat.

Wallet page: Wallet connection interface. Shows available wallets (MetaMask, Coinbase Wallet, WalletConnect), connection status, balance display. In v2, this uses Base wallet adapters instead of Solana.

Marketplace view: Read-only view of current marketplace activity. Shows active jobs, bid counts, status progression.

## 3. ButlerSphere Component

The ButlerSphere is the visual centerpiece of the mobile app — a 3D animated orb that represents the Butler AI agent. It serves as the primary interaction point for voice conversations.

Technical implementation: Built with Three.js via React Three Fiber (@react-three/fiber). The orb is an icosahedron geometry (args: radius 3.2, detail 32) wrapped in a custom ShaderMaterial.

The component structure: ButlerSphere wraps a Canvas with OrbScene inside. The Canvas is configured with antialiasing enabled, alpha transparency, device pixel ratio capped at 2x for performance, and scroll-resize disabled. The component receives an optional ElevenLabs conversation object to access input/output volume for audio reactivity.

Animation entry: The orb container uses Framer Motion for a scale-up animation (scale 0 → 1, opacity 0 → 1) over 1.5 seconds with easeOut easing.

Status indicator: Below the orb, a text indicator shows current state — "Agent Speaking" when the AI is talking, "Listening..." when waiting for user input, or "Ready to talk" when disconnected.

WebGL context loss handling: The component listens for webglcontextlost events and automatically calls forceContextRestore after a 1ms delay, preventing blank screens on mobile devices that aggressively manage GPU resources.

Color system: Two colors (default cyan #0ea5e9 and light cyan #22d3ee) are interpolated via lerp at 5% per frame, allowing smooth color transitions when the orb state changes.

Speed system: Output volume drives animation speed. Target speed is calculated as 0.1 + (1 - (outputVolume - 1)^2) * 0.9. Speed ramps up instantly when volume increases but smoothly decays (10% per frame toward target) when volume drops, creating a natural "excitement then settle" effect.

Uniforms updated per frame: uTime (incremented by delta * 0.5), uAnimation (incremented by delta * speed), uInputVolume, uOutputVolume, uColor1, uColor2.

## 4. Shader Details (orb.vert / orb.frag)

**Vertex Shader (orb.vert)**:

The vertex shader implements simplex noise-based vertex displacement for organic, blobby deformation of the icosahedron.

Simplex 3D noise implementation: A full simplex noise function (snoise) is implemented in GLSL. It uses permutation functions, Taylor inverse square root for normalization, and the standard simplex lattice approach. The implementation produces smooth, gradient noise values in the range of approximately negative one to positive one.

Displacement calculation: The active volume is computed as the maximum of input volume times 1.5 and output volume times 2.0, prioritizing output (AI speaking) over input (user speaking). Noise frequency is fixed at 1.5. Noise amplitude is 0.8 plus active volume times 2.5, meaning the spikes get dramatically larger when audio is active. The noise position combines vertex position scaled by noise frequency with time offset, creating continuously evolving displacement patterns.

The final displacement moves each vertex along its normal by the noise value multiplied by noise amplitude multiplied by active volume. This creates the characteristic "spiky blob" appearance that intensifies with audio activity. When silent, the orb is nearly smooth; when speaking, it becomes dramatically deformed with organic protrusions.

**Fragment Shader (orb.frag)**:

The fragment shader creates the glowing, translucent appearance with Fresnel edge effects.

Color mixing: A dynamic gradient is computed using the dot product of the surface normal with a time-varying direction vector (sin(time), cos(time), sin(time * 0.5)). This creates a continuously shifting color pattern across the surface. The two input colors (uColor1, uColor2) are blended based on this value.

Fresnel glow: Edge glow is calculated using 1 minus the dot product of the view direction and surface normal, squared for intensity. This makes edges glow brighter than the center of the sphere, creating a rim-lighting effect that gives the orb a sense of depth and luminosity.

Core brightness: The overall brightness scales with audio — glow equals 1.2 plus active volume times 1.5. Combined with the Fresnel term, this makes the orb pulse with sound.

Alpha transparency: Base alpha is 0.95, with edges slightly more opaque (plus Fresnel times 0.5). This creates a subtle "gooey" translucency effect while keeping the orb mostly solid.

## 5. ChatScreen Component

The ChatScreen is the primary user interface — a full-screen chat experience combining voice and text input with marketplace integration.

**State management**: The component maintains several pieces of state: transcript (array of messages with id, role, content, timestamp), orbStatus (idle/listening/thinking/speaking), sessionId (UUID for chat persistence), conversations (sidebar history), bidProgress (active bid collection animation), taskExecution (agent working animation), textInput (typed message), stripePayment (payment UI trigger), isSending (text submission lock).

**Session management**: Sessions are identified by UUID generated client-side using crypto.randomUUID with a fallback for SSR environments (timestamp + random string). Session IDs are stored in refs to avoid stale closures in callbacks. The component tracks both userId (from auth context) and wallet address for session association.

**Message persistence**: Every message (user or assistant) is persisted via fire-and-forget POST to /api/chat with sessionId, role, text, wallet address, and userId. The chat session is upserted — created on first message, updated on subsequent ones. The first user message becomes the session title (truncated to 80 characters).

**Conversation history sidebar**: Triggered by sidebarOpen prop or local state. Loads conversation list via GET /api/chat filtered by userId or wallet address. Shows up to 50 most recent sessions. Clicking a conversation loads its messages. New conversation button generates fresh sessionId and clears transcript.

**Voice integration (ElevenLabs)**: The conversation hook from @elevenlabs/react handles the voice connection lifecycle. On connect: orb status set to "listening", toast shown. On disconnect: toast shown if unexpected drop, orb reset to idle. On message: transcribed text added to both user and assistant transcript, assistant messages checked for JSON job data. On mode change: orb status updated to match (listening/speaking). On error: error logged, toast shown, orb reset. Unhandled client tool calls are caught and reported.

**Client tools registered with ElevenLabs**: post_job (parses job data from voice, posts to marketplace), query_butler (forwards text to Butler API), get_job_listings (fetches marketplace jobs), transferFunds (Solana/Base token transfer), getWalletAddress (returns connected wallet).

**Voice toggle**: Tapping the orb toggles voice session. Starting: requests microphone permission, fetches conversation token from /api/elevenlabs/token, starts ElevenLabs session with WebRTC. Stopping: ends session, resets orb.

**Text input**: When no voice session is active, typed messages go directly to Butler API (POST /api/v1/chat). When voice session is active, typed messages are routed through ElevenLabs (conversation.sendUserMessage) so the agent responds with voice.

**Bid Progress Bar**: A glassmorphism-styled progress bar shown during bid collection (15 seconds). Animated gradient bar (indigo → violet → purple) fills from 0 to 100%. Shows countdown timer. Auto-dismisses on completion.

**Task Execution Progress**: Shown after payment confirmation while agent works. Displays animated dots (pulsing opacity) to indicate ongoing work.

**Stripe Payment integration**: Triggered when a job result contains escrow.needs_user_funding flag. Extracts budget amount, job ID, and winner address from job result. Validates winner address as valid Base address (in v2). Renders StripePayment component inline in chat. On success: dismisses payment UI, shows confirmation toast, triggers job execution via POST to /marketplace/execute/{boardJobId}. On error: dismisses payment UI, shows error toast, suggests retry or crypto payment.

**JSON job interception**: Assistant messages are scanned for JSON objects containing a "task" field. If found, the JSON is parsed and automatically posted to the marketplace. This allows the voice agent to output structured job data that gets automatically processed.

**Error handling**: Unhandled promise rejections from ElevenLabs SDK are caught globally to prevent page crashes. Network errors show toast notifications. Payment failures offer retry options.

## 6. VoiceAgent Component

An alternative voice interface component with more features than ChatScreen's built-in voice.

**ElevenLabs ConvAI integration**: Uses @elevenlabs/react useConversation hook. Creates Butler tools that bridge voice to the FastAPI backend: query_butler (sends user query, returns response), get_job_listings (fetches marketplace jobs), check_wallet_status (checks wallet balance).

**Token fetching**: API key never exposed client-side. Server-side /api/elevenlabs/token route fetches signed URL from ElevenLabs API using the secret key. Client receives only the one-time-use token.

**Budget parsing from speech**: The parseBidFromText function extracts bid amounts from spoken text. Supports two formats: structured markers like "BID amount=5 currency=USDC" and natural speech like "bid five USDC". Includes word-to-number conversion for spoken numbers (one through twenty). Handles decimal points ("five point five").

**Session persistence**: Generates session IDs (sess_timestamp_random), stores in localStorage. Loads previous messages from /api/chat on mount. Persists new messages fire-and-forget.

**Voice visualization**: Uses the Orb component with manual volume mode. getInputVolume returns 0.8 when agent is speaking, 0 otherwise. getOutputVolume returns processed value with square root compression and 2.5x scaling for visual impact.

**Base wallet integration (v2)**: Constants for Butler address on Base, target chain ID (84532 for Base Sepolia), USDC stablecoin address and decimals (6). ERC-20 transfer ABI for USDC payments. toBaseUnits function converts decimal strings to proper uint256 values.

**Auto-bid flow**: When a bid is detected in speech, the component automatically initiates an on-chain USDC transfer. Checks wallet connection, switches to Base Sepolia if needed, converts amount to base units, calls writeContract for ERC-20 transfer to Butler address.

## 7. WalletConnectButton Component

Handles wallet connection for the mobile app.

**v1 (current — Solana)**: Lists available Solana wallet adapters: Demo Wallet (hackathon testing), Phantom, Solflare, Coinbase Wallet, WalletConnect. Auto-connects Demo Wallet on mount. Shows installed vs not-installed wallets. Mobile detection (user agent sniffing) changes UI text.

**v2 (planned — Base/Ethereum)**: Will use wagmi + RainbowKit or ConnectKit for Base wallet connection. Supported wallets: MetaMask (most common), Coinbase Wallet (native Base support), WalletConnect v2 (QR code for mobile wallets). Auto-detection of installed wallets. Mobile deep-linking to wallet apps.

**Connection flow**: User taps wallet button → adapter list shown → user selects wallet → select() called to set adapter → connect() called to trigger wallet prompt → on success, connected state propagates through context → on rejection (user denied), error cleared silently → on actual error, error message displayed.

**Device-aware UI**: Mobile shows "tap to open wallet app" hint with smartphone icon. Desktop shows "select your wallet" with monitor icon. WalletConnect always shows QR code icon since it works cross-device.

## 8. Payment Components

**StripePayment component**: Embeds Stripe Elements for payment collection. Creates PaymentIntent via POST /api/stripe/create-payment-intent with jobId, amount (USDC), agentAddress. Renders Apple Pay / Google Pay / card input. In v2, displays 5% surcharge notice for Stripe path.

**Crossmint widget (v2 — new)**: Alternative payment method for crypto-native users. Embeds Crossmint's payment widget. User connects Base wallet and pays USDC directly. No SOTA platform surcharge (Crossmint's own per-transaction fees are negotiated separately and deducted on their side before funds arrive). Funds route through SOTAPaymentRouter.routeCrossmintPayment().

**Payment method selection**: In v2, users see both options side by side: "Pay with Card (+5% fee)" and "Pay with Crypto (no platform fee)". Amount displayed in USDC with equivalent USD for Stripe path. Note: Crossmint charges its own per-transaction fees (negotiated, volume-tiered), but these are handled on Crossmint's side and not added by SOTA.

## 9. Providers

The app wraps all pages in a provider tree (outermost to innermost):

**AuthProvider**: In v1, custom JWT auth with AuthContext providing user, loading state, getIdToken, logout. In v2, replaced with Supabase Auth — email/OAuth login, wallet address linking on profile.

**Base wallet provider (v2)**: Replaces Solana ConnectionProvider + WalletProvider. Uses wagmi + WalletConnect for Base chain. Configures Base Sepolia (testnet) and Base Mainnet networks. Auto-connect enabled.

**QueryClientProvider**: React Query (TanStack Query) with 60-second stale time. Handles server state caching and revalidation.

**ElevenLabs config**: Agent ID from NEXT_PUBLIC_ELEVENLABS_AGENT_ID environment variable. API key kept server-side only.

## 10. API Routes

These are Next.js API routes hosted by the mobile frontend app (not the shared FastAPI backend).

**POST /api/chat**: Save a chat message. Requires sessionId, role, text. Optional wallet, userId. Upserts ChatSession (creates if not exists, sets title from first user message). Creates ChatMessage record. Returns created message with status 201.

**GET /api/chat**: Load chat data. Query params: sessionId (returns messages for session, ordered by createdAt ASC), userId (returns up to 50 sessions for user, ordered by updatedAt DESC), wallet (returns up to 50 sessions for wallet). No params returns 20 most recent sessions.

**GET /api/elevenlabs/token**: Fetch ElevenLabs conversation token. Rate limited: 10 requests per minute per IP (in-memory sliding window). Calls ElevenLabs API with server-side API key. Validates response contains valid token string. Returns 429 on rate limit, 502 on ElevenLabs error.

**POST /api/stripe/create-payment-intent**: Create Stripe PaymentIntent. Validates: jobId or boardJobId required, agentAddress must be valid address, amount must be number between 0 and 10,000. Converts USDC to cents (1:1 ratio), enforces Stripe minimum ($0.50). Stores metadata: jobId, agentAddress, usdcAmountRaw (6 decimal precision), boardJobId, userId. Returns clientSecret.

**POST /api/stripe/webhook**: Handle Stripe payment events. Verifies webhook signature. Idempotency: in-memory map of processed event IDs with 5-minute TTL and 10K max size with pruning. On payment_intent.succeeded: extracts metadata, performs on-chain operations (in v1: mint USDC + fund Solana escrow; in v2: calls SOTAPaymentRouter on Base). Creates Payment record. If on-chain fails: still creates Payment with "pending" status for manual resolution.

**POST /api/stripe/refund**: Process refund for failed job. Authenticated via x-internal-api-key header. Validates job_id, looks up Payment record. Idempotent: returns success if already refunded, 409 if refund in progress. Uses CAS (compare-and-swap) via Prisma transaction: atomically transitions status from funded/pending to refund_requested. Then: on-chain escrow refund (checks deposit state — skips if already refunded or not funded), then Stripe refund (handles already-refunded gracefully). Updates Payment record to "refunded" with all transaction hashes. On failure: marks "refund_failed" with partial results.

**POST /api/auth/login**: Email/password login. Validates email and password strings. Looks up user by lowercase email, verifies password hash. Returns user object and JWT session token.

**POST /api/auth/register**: New user registration. Validates: email must contain @, password 6-1024 characters. Checks uniqueness. Creates user with hashed password. Returns user object and JWT token with status 201.

**GET /api/auth/me**: Get current user. Requires Bearer token in Authorization header. Verifies JWT, looks up user by ID. Returns user object (id, email, name).

## 11. State Management

**React Query patterns**: Used for server state (fetching jobs, agents, marketplace data). Configured with 60-second stale time to reduce unnecessary refetches. Queries are cached by key and automatically revalidated on window focus.

**Auth context**: Provides user object, loading state, getIdToken function, logout function. In v2, backed by Supabase Auth instead of custom JWT. Session persisted in cookies/localStorage.

**Wallet state**: In v1, managed by @solana/wallet-adapter-react context (publicKey, connected, sendTransaction, connection). In v2, managed by wagmi context (address, chainId, isConnected, writeContract, switchChain).

**Local component state**: Transcript array, orb status, sidebar visibility, payment state, bid progress — all managed with useState. Refs used for values needed in callbacks to avoid stale closures (sessionIdRef, addressRef, userIdRef).

**No global state store**: The app intentionally avoids Redux or Zustand. React Query handles server state, contexts handle auth/wallet, and component state handles UI. This keeps the architecture simple for a primarily chat-focused app.
