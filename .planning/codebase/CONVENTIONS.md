# Coding Conventions

**Analysis Date:** 2026-03-14

## Naming Patterns

**Files:**
- TypeScript/Next.js API routes: `route.ts` in `[feature]/route.ts` structure (e.g., `src/app/api/agents/route.ts`)
- React components: PascalCase with `.tsx` extension (e.g., `VoiceAgent.tsx`, `ThemeProvider.tsx`)
- Utility/library files: lowercase with hyphens for compound names (e.g., `validators.ts`, `auth.ts`)
- Python modules: snake_case (e.g., `base_agent.py`, `task_memory.py`)
- Python test files: `test_*.py` or `*_test.py` convention

**Functions:**
- TypeScript: camelCase for all functions (e.g., `getCurrentUser`, `validateApiKey`, `parseCapabilities`)
- TypeScript: PascalCase for React component functions (e.g., `ThemeProvider`, `VoiceAgent`)
- Python: snake_case for functions (e.g., `get_initial_theme`, `create_butler_tools`)
- Python: PascalCase for classes (e.g., `ButlerAgent`, `BaseArchiveAgent`)

**Variables:**
- TypeScript: camelCase for all variable names (e.g., `sessionId`, `pendingBid`, `lastBidKey`)
- Constants: UPPERCASE_WITH_UNDERSCORES (e.g., `THEME_STORAGE_KEY`, `STABLECOIN_DECIMALS`, `JWT_SECRET`)
- React state: camelCase with descriptive names reflecting state (e.g., `isStarting`, `hasStarted`, `isSendingBid`)
- Python: snake_case (e.g., `session_id_ref`, `pending_bid`, `last_bid_key`)

**Types:**
- TypeScript: PascalCase interfaces and types (e.g., `ThemeContextValue`, `VoiceAgentProps`, `SessionPayload`)
- Python: PascalCase for enums and dataclasses (e.g., `AgentCapability`, `BidDecision`, `ActiveJob`)

## Code Style

**Formatting:**
- ESLint v9 with Next.js core-web-vitals and TypeScript support
- Config: `eslint.config.mjs` at repository root
- No Prettier config detected — code formatted via ESLint rules

**Linting:**
- Tool: ESLint with `eslint-config-next` and `eslint-config-next/typescript`
- Key ignores: `.next/**`, `contracts/**`, `next-env.d.ts`
- Enforces Next.js best practices and TypeScript strict rules

**TypeScript Settings:**
- Target: ES2020
- Strict mode: **Enabled** in main codebase (`tsconfig.json`), **Disabled** in mobile frontend (`mobile_frontend/tsconfig.json`)
- Main codebase path alias: `@/*` → `./src/*`
- Mobile frontend path alias: `@/*` → `./*`

## Import Organization

**Order:**
1. External dependencies (React, Next, libraries)
2. Type imports and interfaces (marked with `import type` when appropriate)
3. Internal library imports (`@/lib/*`)
4. Internal component imports (`@/components/*`)
5. Relative imports (when unavoidable)

**Path Aliases:**
- Main app: `@/` resolves to `src/`
- Mobile frontend: `@/` resolves to root directory
- Used consistently across all `.ts` and `.tsx` files

**Example pattern from `src/app/api/agents/route.ts`:**
```typescript
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { agentSchema } from "@/lib/validators";
import { getCurrentUser } from "@/lib/auth";
```

## Error Handling

**Patterns:**
- API routes: Wrap in try-catch, return `NextResponse.json()` with error object and HTTP status
- Error format: `{ error: "Message" }` with appropriate status codes (400, 401, 403, 500)
- Validation errors: `{ error: fieldErrors }` from Zod `safeParse().error.flatten()`
- Logging: `console.error("Context:", error)` in catch blocks for debugging
- No custom error classes except `AuthError` in auth layer

**Example from `src/app/api/agents/route.ts`:**
```typescript
try {
  // operation
} catch (error) {
  console.error("Error fetching agents:", error);
  return NextResponse.json({ error: "Failed to fetch agents" }, { status: 500 });
}
```

**Validation Error Handling:**
```typescript
const parsed = agentSchema.safeParse(body);
if (!parsed.success) {
  return NextResponse.json(
    { error: parsed.error.flatten().fieldErrors },
    { status: 400 }
  );
}
```

**Custom Error Classes:**
- `AuthError` in `src/lib/auth.ts` extends Error with status code property
- Thrown in auth middleware, caught and converted to HTTP responses in routes

## Logging

**Framework:** `console.error()`, `console.log()`, `console.warn()`
- No structured logging framework used
- Console methods called directly throughout codebase

**Patterns:**
- **Errors:** `console.error("Context:", error)` - always includes context label
- **Info:** `console.log("Message:", value)` - used sparingly, mainly for debugging
- **Warnings:** `console.warn("Issue")` - less common
- Python agents: Use Python's `logging` module with `logger.getLogger(__name__)`

**Examples from code:**
```typescript
// src/app/api/agents/route.ts
console.error("Error fetching agents:", error);

// mobile_frontend/src/context/AuthContext.tsx
console.warn('Failed to load chat history:', err);

// mobile_frontend/src/components/VoiceAgent.tsx
console.log('📤 Sending to Butler:', query);
console.log('✅ Butler Agent response:', data);
console.error('❌ Butler Agent error:', error);
```

**Python logging:**
```python
# agents/src/butler/agent.py
logger = logging.getLogger(__name__)
```

## Comments

**When to Comment:**
- Function headers: Docstrings for functions, especially public/exported ones
- Complex logic: Explain *why*, not *what* (code shows what)
- TODOs/FIXMEs: Not used systematically in codebase
- Section headers: Use for organizing large blocks (e.g., `// ── API Key Generation & Validation ──`)

**JSDoc/TSDoc:**
- Minimal use observed
- Interfaces and types documented inline where they appear
- Function comments: Brief descriptions of purpose

**Example from `src/lib/validators.ts`:**
```typescript
/** Validate a base-58 Solana address (regex, no checksum). */
export function isValidSolanaAddress(addr: string): boolean {

/** Validate an HTTP(S) URL string. */
export function isValidHttpUrl(s: string): boolean {

/** Safely parse a JSON-encoded capabilities string. Returns string[] or fallback. */
export function parseCapabilities(raw: string | null | undefined): string[] {
```

## Function Design

**Size:** No strict limits observed; functions range from 5-50 lines
- Single-responsibility principle applied (each function does one thing)
- Helper functions extracted for repeated logic

**Parameters:**
- Named parameters preferred
- Type annotations always used in TypeScript
- Interface types for complex parameter objects

**Return Values:**
- Explicit return types always specified in TypeScript
- Null/undefined returned for not-found scenarios
- Promise types for async functions
- Objects for multiple return values

**Example from `src/lib/auth.ts`:**
```typescript
export function generateApiKey(): GeneratedApiKey {
  // Structured return type

export async function validateApiKey(fullKey: string): Promise<ValidatedApiKey | null> {
  // Explicit return type with union for null

export async function getCurrentUser(request: Request): Promise<User | null> {
  // Async with null return
```

## Module Design

**Exports:**
- Named exports preferred over default exports
- Common pattern: `export function name() {}` and `export interface Name {}`
- One responsibility per file

**Barrel Files:**
- Not heavily used
- Direct imports preferred (e.g., `import { getCurrentUser } from "@/lib/auth"`)

**Examples of module structure:**
- `src/lib/auth.ts` - Authentication utilities only
- `src/lib/validators.ts` - Validation schemas and helpers
- `src/lib/utils.ts` - Utility functions (e.g., `cn()` for class merging)
- `src/components/theme-provider.tsx` - Theme context and hooks

## React/Next.js Conventions

**Client Components:**
- Marked with `"use client"` directive when needed (hooks, event handlers)
- Example: `mobile_frontend/src/context/AuthContext.tsx`

**Context Providers:**
- createContext with TypeScript type
- Provider component and custom hook for usage
- Custom hook throws error if used outside provider
- Pattern: `useContext()` guard with helpful error message

**Example from `src/components/theme-provider.tsx`:**
```typescript
export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used inside ThemeProvider");
  }
  return context;
}
```

## API Route Conventions

**Structure:**
- Exports named async functions: `GET`, `POST`, `PUT`, `DELETE`, etc.
- Function signature: `async function METHOD(req: Request): Promise<NextResponse>`
- Path-based routing: File location determines route

**Request Handling:**
- Extract search params: `new URL(req.url).searchParams`
- Parse body: `await req.json()`
- Return: `NextResponse.json(data)` or `NextResponse.json(error, { status })`

**Authentication:**
- Use `getCurrentUser(req)` or `requireAuth(req)` from `@/lib/auth`
- Return 401 for unauthenticated requests
- Return 403 for insufficient permissions

---

*Convention analysis: 2026-03-14*
