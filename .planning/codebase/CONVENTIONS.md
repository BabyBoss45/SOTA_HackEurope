# Coding Conventions

**Analysis Date:** 2026-03-14

## Naming Patterns

**Files:**
- TypeScript/React components: `kebab-case.tsx` for components, `camelCase.ts` for utilities
- Examples: `src/components/auth-provider.tsx`, `src/components/theme-toggle.tsx`, `src/lib/utils.ts`
- API routes: `route.ts` in directory structure matching endpoint path
- Example: `src/app/api/agents/route.ts` for `/api/agents`
- Python files: `snake_case.py` for all modules and functions
- Example: `agents/src/butler/agent.py`, `agents/src/shared/base_agent.py`

**Functions:**
- TypeScript/JavaScript: `camelCase`
- Examples: `generateApiKey()`, `validateApiKey()`, `getCurrentUser()`, `encryptApiKey()`
- React hooks: `camelCase` prefixed with `use`
- Examples: `useAuth()`, `useTheme()`, `useConversation()`
- Exported utility functions: `camelCase`
- Example: `cn()` utility function combines clsx and tailwindMerge
- Python functions: `snake_case`
- Examples: `get_keypair()`, `place_bid()`, `create_wallet_from_env()`

**Variables:**
- TypeScript/JavaScript: `camelCase` for constants and mutable variables
- Example: `const TOKEN_KEY = "sota_session_token"`
- Python: `UPPER_SNAKE_CASE` for module-level constants
- Example: `BUTLER_SYSTEM_PROMPT`, `SOLANA_CLUSTER = "devnet"`

**Types:**
- TypeScript interfaces: `PascalCase`
- Examples: `AuthUser`, `AuthContextType`, `GeneratedApiKey`, `ValidatedApiKey`, `SessionPayload`
- TypeScript type aliases: `PascalCase`
- Example: `type Theme = "dark" | "light"`
- Python enums: `PascalCase` class with `UPPER_SNAKE_CASE` members
- Example: `AgentCapability(str, Enum)` with `PHONE_CALL = "phone_call"`
- Zod schemas: `camelCase` with `Schema` suffix or no suffix based on type export
- Examples: `authSchema`, `agentSchema`, `agentUpdateSchema`, `profileSchema`

## Code Style

**Formatting:**
- No explicit prettier config found
- Next.js eslint config is primary source of formatting rules
- Code uses consistent 2-space indentation across TypeScript/React/CSS
- Lines follow readability patterns without strict length enforcement

**Linting:**
- ESLint configuration: `eslint.config.mjs` (flat config format)
- Extends: `eslint-config-next/core-web-vitals` and `eslint-config-next/typescript`
- Run: `npm run lint` or `pnpm lint`
- Ignores: `.next/`, `out/`, `build/`, `contracts/`, Next.js generated files

**TypeScript Strictness:**
- Main tsconfig.json: `"strict": true`
- Mobile frontend tsconfig.json: `"strict": false`
- Both use ES2020 target with ESNext module
- Path aliases configured: `@/*` maps to `./src/*` in main app, `./*` in mobile_frontend

## Import Organization

**Order:**
1. External React/Next.js imports
   - `import React, { ... } from "react"`
   - `import { ... } from "next/..."`
2. External third-party library imports
   - `import { ... } from "@solana/web3.js"`
   - `import { ... } from "framer-motion"`
3. Internal application imports using path aliases
   - `import { cn } from "@/lib/utils"`
   - `import { useAuth } from "@/components/auth-provider"`

**Path Aliases:**
- Main app: `@/*` → `./src/*`
- Mobile frontend: `@/*` → `./*`
- Examples in use: `@/lib/utils`, `@/components/button`, `@/lib/validators`

## Error Handling

**Patterns:**
- Try-catch blocks wrap async operations and API calls
- Example pattern in `src/components/auth-provider.tsx`:
  ```typescript
  fetch("/api/auth/login", {...})
    .then((res) => (res.ok ? res.json() : null))
    .catch(() => localStorage.removeItem(TOKEN_KEY))
    .finally(() => setLoading(false));
  ```
- API routes return NextResponse with error objects containing `error` field
  - Example: `return NextResponse.json({ error: "Unauthorized" }, { status: 401 })`
- Custom error classes for domain-specific errors
  - Example: `AuthError` in `src/lib/auth.ts` extends Error with status code property
- Silent failures permitted for non-critical operations
  - Example comment: `// Cookie-setting is best-effort; API Bearer auth still works`
- Zod validation with `.safeParse()` returns error flattening
  - Example: `parsed.error.flatten().fieldErrors` in validation routes
- Promise.all() used for parallel async operations
  - Example in `src/app/api/agents/route.ts` for fetching agent owners

## Logging

**Framework:** `console.*` methods directly

**Patterns:**
- `console.error()` for error logging with context
- Example: `console.error("Error fetching agents:", error)`
- No structured logging library detected in main codebase
- Python agents use `logging.getLogger(__name__)` pattern
- Example in `agents/src/butler/agent.py`: `logger = logging.getLogger(__name__)`

## Comments

**When to Comment:**
- Document non-obvious logic or business logic
- Examples in codebase: Section headers like `// ═══════════════════════════════════════════════════════════` separate logical units
- Inline comments explain intent rather than "what" the code does
- Example in `src/lib/auth.ts`: `// 7 days` next to expiration time
- JSDoc-style comments over public APIs and complex functions (sparse usage)

**JSDoc/TSDoc:**
- Minimal JSDoc usage in TypeScript codebase
- When used, documents complex functions and public APIs
- Example: Python docstrings used liberally for agent classes
  - `"""Base Archive Agent -- Solana Edition\n\nAbstract base class...`

## Function Design

**Size:** Functions kept to single responsibility; complex operations delegated
- Example: `validateApiKey()` handles lookup, validation, and state update separately
- Utility functions are small: `cn()` is 2 lines, `hashPassword()` is 1 line

**Parameters:**
- Destructuring used for object parameters
- Example: `export function AuthProvider({ children }: { children: React.ReactNode })`
- Type annotations required in TypeScript files
- Python uses type hints via pydantic and native typing

**Return Values:**
- Functions explicitly return null for failure cases rather than throwing
- Examples: `validateApiKey()` returns `null` on failure, not exception
- React components return JSX or null
- Async functions return Promise-wrapped types
- Example: `async function GET(req: Request): Promise<NextResponse>`

## Module Design

**Exports:**
- Named exports preferred over default exports
- Example: `export function cn(...)` rather than `export default function`
- Exception: React context providers occasionally use named exports
- Barrel files used for component grouping (not heavily used)

**Barrel Files:**
- Not extensively used in this codebase
- Direct imports preferred
- Example: Import directly from `@/lib/auth` not from `@/lib` index

## Prisma Models

**Convention:**
- PascalCase model names
- camelCase field names
- Relationships use `@relation()` with explicit field references
- Example: `owner User @relation(fields: [ownerId], references: [id])`
- Comments inline to document purpose of fields
- Example: `// Agent's payment wallet address` for walletAddress field
- Timestamps: `createdAt` with `@default(now())`, `updatedAt` with `@updatedAt`

## Validation

**Primary Tool:** Zod schema validation library
- Example: `agentSchema` in `src/lib/validators.ts`
- Helper functions provide reusable validators
- Examples: `isValidSolanaAddress()`, `isValidHttpUrl()`
- Optional string transformation removes empty strings before validation
- Example in validators: `.transform((v) => (v.trim() === "" ? undefined : v))`

## Context and Providers

**React Context Pattern:**
- Context created with `createContext<Type | undefined>(undefined)`
- Provider component handles initialization and state management
- Custom hook (`useContext`) wraps access with error checking
- Examples: `AuthProvider`, `ThemeProvider`
- Error thrown if hook used outside provider
- Example: `throw new Error("useAuth must be used within an AuthProvider")`

## API Key Management

**Convention:**
- API keys never stored in plaintext
- Encrypted with AES-256-CBC using `ENCRYPTION_KEY` from environment
- Hash stored separately using SHA-256 for comparison without decryption
- Example in `src/lib/auth.ts`: `generateApiKey()`, `encryptApiKey()`, `decryptApiKey()`

## Session Management

**Convention:**
- Session tokens are base64-encoded JSON with SHA-256 signature
- Token format: `Buffer.from("${data}.${signature}").toString('base64')`
- Tokens include expiration (7 days default)
- Custom implementation rather than reliance on JWT library
- Validation checks signature and expiration time
- Example in `src/lib/auth.ts`: `createSessionToken()`, `verifySessionToken()`

---

*Convention analysis: 2026-03-14*
