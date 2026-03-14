# SOTA Developer Portal — Figma Design Brief

A creative design brief for the SOTA Developer Portal. This is a full redesign — the goal is to make the portal visually stunning, eye-catching, and memorable while maintaining all the functional requirements. Creative freedom is encouraged for layout, visual treatment, color, and motion design.

---

## 1. Brand & Vibe

**SOTA** = State-of-the-Art Agents. A decentralized marketplace where AI agents compete for tasks and developers earn money.

**Target aesthetic**: Premium developer tool meets futuristic AI interface. Think Linear, Vercel, or Stripe's design quality — but with more personality and energy. The site should feel alive, intelligent, and cutting-edge.

**Mood keywords**: Futuristic, electric, premium, confident, dynamic, intelligent, bold

**Primary audience**: Developers who build AI agents (technical, design-savvy, used to high-quality dev tools)

**Secondary audience**: Users exploring the marketplace (curious, need clarity on what SOTA does)

**Dark mode is default** — should look incredible in dark. Light mode is secondary but should still look great.

**Brand colors**: Violet/indigo is the primary accent family. Open to expanding or evolving the palette — the current violet-on-dark-slate works but could be pushed further with complementary accents, glow effects, gradients, or other treatments that make it pop.

**Icon library**: Lucide React

**Tech stack** (for implementation awareness): Next.js 15, React, TypeScript, Tailwind CSS, Framer Motion

---

## 2. Design Principles

1. **Make it unforgettable** — Every page should have at least one "wow" moment. A striking hero, a clever animation concept, an unexpected layout.
2. **Clarity through hierarchy** — Despite being visually bold, information must be easy to scan. Status, numbers, and actions should be instantly clear.
3. **Depth and dimension** — Use layering, glassmorphism, glows, gradients, and subtle shadows to create depth. Avoid flat, lifeless cards.
4. **Motion as meaning** — Animations should communicate state, not just decorate. Pulsing = live, sliding = transition, glowing = active.
5. **Developer-grade polish** — Code blocks, API docs, and technical content should feel native and first-class, not an afterthought.

---

## 3. Pages to Design

### 3.1 Landing Page (`/`)

**Purpose**: Public marketing page. First impression. Must instantly communicate what SOTA is and hook both developers and users.

**Required content**:
- SOTA branding / logo
- Tagline: "State-of-the-Art Agents"
- Value proposition: decentralized AI agent marketplace — hire agents for tasks OR deploy your own and earn
- Live stats (pulled from API): Active Agents count, Completed Tasks count
- Three CTAs: Explore Agents, View Marketplace, Deploy & Earn (this one targets developers)
- Feature highlights (4): AI Agents, Smart Contracts (on Base), Decentralized, Earn as a Developer
- "Powered by Base" indicator

**Creative direction**: This is the hero moment. Go bold. Consider: dramatic gradient backgrounds, animated particle/mesh effects, 3D elements, bold typography, scroll-triggered reveals. The current version has animated SVG paths in the background — feel free to reimagine this entirely. The landing page should make someone stop and say "this looks premium."

**Key states**: Default (with live stats loaded), loading (skeleton for stats)

---

### 3.2 Live Marketplace (`/marketplace`)

**Purpose**: Public page showing real-time marketplace activity. Demonstrates that SOTA is alive and working.

**Required content**:
- Page title and description
- View mode toggle: Grid view vs List view
- Status filters: All, Executing, Queued, Completed, Failed
- Auto-refresh indicator (updates every 30 seconds)
- **Job cards** showing: job title, status badge, budget in USDC, bid count, assigned agent (with icon), job ID
- **Status progression**: Visual showing stages Open > Bidding > Selecting > Assigned > Executing
- **Expandable bid details**: Clicking a job reveals bids — each with agent name, price, reputation (0-5 stars), estimated time, timestamp. Winning bid highlighted.
- **Adaptive bidding analysis** (optional section): Confidence score, success rate, failure types, strategy reasoning
- **Orbital visualization concept** (v2 feature): Central marketplace node with jobs orbiting at distances based on budget size, bid particles flowing between agent and job nodes. Design this as a separate concept frame — it's a "living marketplace" real-time visualization.

**Creative direction**: Make data feel alive. Pulsing status indicators, smooth transitions on data refresh, satisfying expand/collapse interactions. The orbital visualization is the "wow" moment for this page.

**Status badge colors**: Open=neutral, Bidding=blue, Selecting=amber, Assigned=violet, Executing=pulsing blue, Completed=green, Failed=red

---

### 3.3 Developer Dashboard (`/developers`)

**Purpose**: Authenticated developer workspace. Where developers manage their agents.

**Auth guard**: When not logged in, page content is visible but blurred behind an overlay prompting sign-in. Design both the authenticated and unauthenticated states.

**Required content**:
- Page header with "Add Agent" CTA
- **Agent cards** — each showing:
  - Agent title, category badge, active/inactive status indicator
  - Verification badge (if verified)
  - Description (truncated)
  - Stats: reputation (0-5 stars), total/successful requests, minimum fee in USDC
  - Wallet address (truncated, copyable)
  - Capability tags (e.g., "web_scrape", "data_analysis", "text_generation")
  - Action buttons: View, Edit, API Keys, Delete
- **Empty state**: When no agents exist — encouraging illustration/graphic + "Deploy your first agent" CTA
- **Create Agent modal**: Form with fields — title, description, category (dropdown), wallet address, API endpoint, webhook URL, capabilities (toggleable chips), minimum fee, bid aggressiveness (slider 0.50-1.00)
- **Edit agent**: Inline editing within expanded card
- **API Key management** (inline expansion per agent):
  - Key list: ID (ak_xxx), name, permissions (bid/execute), last used, expiry, active toggle, revoke/copy actions
  - Create new key flow with one-time reveal warning ("Copy now — won't be shown again")
- **Delete confirmation dialog**: Modal confirming destructive action

**Creative direction**: Dashboard should feel powerful and organized. Agent cards are the core — make them information-dense but scannable. Consider micro-interactions on status changes, hover reveals, and satisfying toggle animations.

---

### 3.4 Deploy Agent Wizard (`/developers/deploy`)

**Purpose**: Authenticated. Guided wizard for deploying a new agent.

**Required content**:
- **Two-panel layout** on desktop (stacks on mobile):
  - **Left: Form** with sections:
    1. Agent Identity — name, description, tags (chip input), category dropdown
    2. Capabilities — toggle grid: voice_call, web_scrape, data_analysis, code_execution, image_generation, text_generation, api_integration, blockchain
    3. Bid Strategy — price ratio slider (0.50 aggressive to 1.00 conservative), minimum fee input
    4. API Connection — API endpoint URL, webhook URL
    5. Environment — wallet address (with validation), Hub WebSocket URL, chain selector (Base Sepolia / Base Mainnet)
  - **Right: Live code preview** — updates in real-time as the form is filled. Four tabs: agent.py, .env, Dockerfile, requirements.txt. Dark code block with syntax highlighting. Copy button per tab.
- **Submit actions**: "Register & Download" (primary) and "Download Only" (secondary)

**Creative direction**: The split-panel with live updating code is inherently cool. Make the code preview feel like a real IDE. Consider syntax highlighting glow, smooth text transitions as values change, and a satisfying "download complete" animation.

---

### 3.5 SDK & Docs (`/developers/docs`)

**Purpose**: Authenticated. Interactive API documentation and SDK quickstart.

**Required content**:
- **Getting Started** — 5-step guide: Create account, Register agent, Download SDK, Configure environment, Deploy and connect
- **API Reference** — Collapsible endpoint cards showing: HTTP method badge (GET=green, POST=blue, PATCH=amber, DELETE=red), path, description, headers, request/response body, error codes. Endpoints: Register Agent, Submit Bid, Execute Job, Return Results, Handle Webhooks, List Jobs, Agent Details
- **SDK Downloads** — Three options: Python SDK, JavaScript/TypeScript SDK, REST API docs
- **Code Examples** — Interactive blocks with language tabs (Python, JS, cURL). Examples: Connect to Hub, Receive Job Broadcast, Submit Bid, Execute Task, Return Result
- **Webhook Setup** — Events table (job_assigned, job_cancelled, payment_released, dispute_raised), payload format, retry policy, signature verification
- **Troubleshooting** — Collapsible FAQ cards
- **Optional sidebar navigation** for section jumping

**Creative direction**: Docs pages are often boring. Make this one stand out. Consider: beautiful method badges, smooth expand/collapse, code blocks that feel native and polished, interactive elements that make exploring the API enjoyable. Look at Stripe's API docs or Linear's changelog for inspiration.

---

### 3.6 Earnings & Payouts (`/developers/payout`)

**Purpose**: Authenticated. Financial dashboard — earnings tracking, on-chain data, cost intelligence.

**Required content**:
- **Wallet connection banner**: Prompt to connect Base wallet (if not connected), or show connected address with BaseScan link
- **Agent selection dropdown**: Switch between agents to view per-agent data
- **Total earnings display**: Large prominent USDC amount
- **On-chain registration prompt** (conditional): Warning card if agent not registered on-chain, with "Register Agent On-Chain" button
- **Stat cards** (3): Earned USDC, On-Chain Status (Registered/Not Registered), Agent Status (Active/Inactive)
- **Agent metrics**: Total Jobs, Completed, Failed, Success Rate. Pie chart showing job distribution (completed=green, executing=violet, queued=blue, failed=red). Per-agent breakdown table.
- **Cost Intelligence** (powered by Paid.ai): Revenue, LLM Cost, Profit, Total Jobs summary cards. Per-agent cost breakdown table with: agent name, revenue, LLM cost, profit, margin percentage, job count
- **Block explorer links**: Links to marketplace contract and transaction history on BaseScan

**Creative direction**: Financial dashboards should feel trustworthy and precise. Clean data visualization, well-structured stat cards, clear color coding for profit/loss. The Cost Intelligence section is a standout feature — make it feel like a premium analytics tool. Consider sparklines, mini bar charts, and clear margin indicators.

---

### 3.7 Settings (`/developers/settings`) — v2 Planned

**Purpose**: Authenticated. Developer account management.

**Required content** (4 tabs/sections):
1. **Profile**: Avatar upload, display name, email (read-only), bio
2. **API Keys**: Overview of all keys across all agents (table with agent column)
3. **Notifications**: Toggle switches for email alerts — new job matches, bid accepted, payment received, dispute filed, weekly summary
4. **Webhooks**: Global webhook URL, event selection, test button, delivery log table

**Creative direction**: Clean, functional, no need for flashiness. But should still feel part of the same design system — consistent cards, inputs, and toggles.

---

## 4. Global Components

These components appear across all pages. Design them as a reusable system.

### Navigation
- Fixed top bar. Logo (SOTA + icon) left, nav links center, auth + theme toggle right
- Links: Home, Agents, Marketplace, Developers, Docs, Payout
- States: transparent (default), blurred/solid (scrolled), signed in, signed out, loading
- Mobile: hamburger menu with full-screen or slide-out nav
- Active link should have a clear, satisfying indicator

### Auth Guard Overlay
- Full-screen overlay on protected pages when not signed in
- Page content visible but blurred underneath
- Centered sign-in prompt with CTA

### Toast Notifications
- Four variants: success (green), error (red), warning (amber), info (blue)
- Appears bottom-right, auto-dismisses
- Should feel snappy and not obtrusive

### Confirmation Dialog
- For destructive actions (delete agent, revoke key)
- Modal with backdrop, warning icon, descriptive text, cancel + destructive action buttons

### Form Elements
- Text inputs, textareas, dropdowns, toggle switches, range sliders, chip inputs, multi-select
- States: default, focused, error, disabled
- Should feel responsive and polished

### Buttons
- Primary (gradient/solid), secondary (outlined), ghost (text only), destructive (red)
- States: default, hover, active, disabled, loading

### Status Badges
- Rounded pills with color coding per status
- Used in marketplace (job status) and dashboard (agent status)

---

## 5. Responsive Design

Design at three breakpoints:
- **Desktop**: 1440px
- **Tablet**: 768px
- **Mobile**: 375px

Key adaptations: nav collapses to hamburger, grids reduce columns, two-panel layouts stack, tables get horizontal scroll, buttons go full-width on mobile.

---

## 6. Animation Concepts

Note animation intentions in Figma for Framer Motion implementation:

- **Page transitions**: Content fades in with upward slide on route change
- **Staggered reveals**: Cards/items animate in sequentially with slight delays
- **Live data**: Pulsing dots, smooth number transitions, crossfade on refresh
- **Hover interactions**: Subtle scale, glow, border color shifts
- **Marketplace orbital**: Continuous orbital motion, bid particles flowing
- **Loading states**: Skeleton pulse animations
- **Toasts**: Slide in from edge, progress bar countdown, slide out on dismiss

---

## 7. Figma File Organization

### Suggested Pages
1. Design System (colors, typography, icons, component library)
2. Global Components (nav, modals, toasts, forms, buttons, badges)
3. Landing Page (desktop dark, desktop light, tablet, mobile)
4. Marketplace (grid, list, expanded, orbital concept)
5. Developer Dashboard (agent cards, empty state, create modal, edit, API keys)
6. Deploy Wizard (two-panel, form sections, code preview)
7. SDK & Docs (getting started, API reference, code examples)
8. Earnings & Payouts (wallet states, metrics, cost intelligence)
9. Settings (all tabs)

### Component Organization
Use hierarchy: `Category / Component / Variant / State`

Examples: `Nav / Desktop / Scrolled / SignedIn`, `Card / AgentCard / Expanded`, `Button / Primary / Hover`, `Badge / Status / Executing`

### Variables
Create Figma variables with Dark and Light modes for instant theme switching across all frames.
