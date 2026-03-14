# Testing Patterns

**Analysis Date:** 2026-03-14

## Test Framework

**Runner:**
- Test framework: Not detected
- No vitest, jest, or mocha config found in either main app or mobile_frontend
- Package.json scripts show no test command in main app
- Mobile frontend has placeholder test script: `"test": "echo \"Error: no test specified\" && exit 1"`

**Assertion Library:**
- Not detected in current setup

**Run Commands:**
```bash
pnpm test              # Not implemented - would fail with "Error: no test specified"
```

## Test File Organization

**Location:**
- No test files found in codebase
- Search for `*.test.*` and `*.spec.*` returned no results in src/ or app/ directories
- No `__tests__` directories detected
- Test infrastructure not yet implemented

**Naming Convention (if implemented):**
- Recommend: `[filename].test.ts` co-located with source files
- Alternative: Separate `__tests__` directory per module

**Structure:**
- Would follow Next.js recommended patterns if/when implemented
- Suggest placing tests adjacent to source files for maintainability

## Test Structure (Recommended Pattern)

Based on codebase patterns, recommended test structure would be:

```typescript
// Example: src/lib/auth.test.ts
describe('auth module', () => {
  describe('generateApiKey', () => {
    it('generates key with correct format', () => {
      // test implementation
    })
  })

  describe('validateApiKey', () => {
    it('returns null for invalid key', async () => {
      // test implementation
    })

    it('returns ValidatedApiKey for valid key', async () => {
      // test implementation
    })
  })
})
```

## Mocking

**Framework:** None configured
- Would require addition of mocking library (vitest, jest, or sinon)

**Patterns (Recommended):**
```typescript
// Example: Mocking Prisma client
const mockPrisma = {
  agent: {
    findMany: vi.fn(),
    create: vi.fn(),
  },
  user: {
    findUnique: vi.fn(),
  },
}

// Example: Mocking fetch (browser API)
global.fetch = vi.fn(async () => ({
  ok: true,
  json: async () => ({ /* response data */ }),
}))
```

**What to Mock:**
- External API calls (Solana RPC, third-party services)
- Database operations (Prisma queries)
- Browser APIs (localStorage, fetch)
- Authentication flows (getCurrentUser, validateApiKey)

**What NOT to Mock:**
- Pure utility functions (`cn()`, `hashPassword()`, validators)
- Business logic validation (Zod schemas)
- Component rendering logic (unless testing side effects)

## Fixtures and Factories

**Test Data (Recommended Pattern):**
```typescript
// Example: Factory for test agents
function createTestAgent(overrides?: Partial<Agent>): Agent {
  return {
    id: 1,
    title: 'Test Agent',
    description: 'A test agent for testing',
    ownerId: 1,
    createdAt: new Date(),
    updatedAt: new Date(),
    ...overrides,
  }
}

function createTestUser(overrides?: Partial<User>): User {
  return {
    id: 1,
    email: 'test@example.com',
    name: 'Test User',
    passwordHash: hashPassword('password'),
    createdAt: new Date(),
    ...overrides,
  }
}
```

**Location (Recommended):**
- `__tests__/fixtures/` for shared fixtures
- Or co-located `*.fixtures.ts` files next to test files
- Example: `src/lib/__tests__/auth.fixtures.ts` for auth test fixtures

## Coverage

**Requirements:** No coverage enforcement currently in place

**View Coverage (when implemented):**
```bash
pnpm test --coverage        # Once test framework is added
```

**Target Recommendations:**
- Functions with multiple branches (auth, validation): 80%+ coverage
- API routes: 70%+ coverage
- UI components: 50%+ coverage
- Utilities: 90%+ coverage

## Test Types

**Unit Tests (Recommended Approach):**
- Test isolated functions without external dependencies
- Examples for implementation: `validateApiKey()`, `generateApiKey()`, `cn()`, validators
- Scope: Single function or small module
- Mocked dependencies: Prisma, external APIs
- Location: `src/lib/__tests__/` or `.test.ts` co-located

**Integration Tests (Recommended Approach):**
- Test API routes with mocked database and auth
- Examples for implementation: `GET /api/agents`, `POST /api/agents`
- Scope: Route handler + validators + database
- Mocked dependencies: Prisma, external services
- Real: NextResponse, error handling
- Location: `src/app/api/__tests__/` mirroring route structure

**E2E Tests (Not Currently Implemented):**
- Framework: Not present (could add playwright or cypress)
- Scope: User workflows (login → create agent → fetch → update)
- Would test: Full request/response cycles with real database
- Recommendation: Consider adding for critical user journeys

## Common Patterns (Recommended)

**Async Testing:**
```typescript
// Recommended approach based on codebase patterns
describe('validateApiKey', () => {
  it('validates active API key', async () => {
    // Setup
    const testKey = 'ak_test.secret'
    const mockApiKey = { /* ... */ }
    mockPrisma.agentApiKey.findFirst.mockResolvedValue(mockApiKey)

    // Execute
    const result = await validateApiKey(testKey)

    // Assert
    expect(result).toEqual({ agent: /* ... */ })
  })

  it('returns null for expired key', async () => {
    const expiredKey = { expiresAt: new Date(Date.now() - 1000) }
    mockPrisma.agentApiKey.findFirst.mockResolvedValue(expiredKey)

    const result = await validateApiKey('expired_key')

    expect(result).toBeNull()
  })
})
```

**Error Testing:**
```typescript
// Test error cases and edge conditions
describe('getCurrentUser', () => {
  it('returns null when no auth header present', async () => {
    const request = new Request('http://localhost/api/test')
    const result = await getCurrentUser(request)
    expect(result).toBeNull()
  })

  it('returns null for invalid bearer token', async () => {
    const request = new Request('http://localhost/api/test', {
      headers: { Authorization: 'Bearer invalid_token' },
    })
    const result = await getCurrentUser(request)
    expect(result).toBeNull()
  })

  it('throws AuthError for missing permission', async () => {
    const request = new Request('http://localhost/api/test', {
      headers: { Authorization: 'ApiKey valid_key_without_permission' },
    })

    expect(async () => {
      await requireApiKeyAuth(request, 'admin')
    }).rejects.toThrow('API key does not have admin permission')
  })
})
```

**Zod Schema Testing:**
```typescript
// Test validation schemas
describe('agentSchema', () => {
  it('validates correct agent data', () => {
    const validData = {
      title: 'Test Agent',
      description: 'A valid test agent',
      capabilities: '["voice_call"]',
      category: 'blockchain',
    }

    const result = agentSchema.safeParse(validData)
    expect(result.success).toBe(true)
    expect(result.data).toEqual(validData)
  })

  it('rejects agent with short title', () => {
    const invalidData = {
      title: 'AB', // Too short
      description: 'A valid test agent',
      capabilities: '["voice_call"]',
    }

    const result = agentSchema.safeParse(invalidData)
    expect(result.success).toBe(false)
    expect(result.error.flatten().fieldErrors.title).toBeDefined()
  })

  it('rejects agent with invalid Solana address', () => {
    const invalidData = {
      title: 'Test Agent',
      description: 'A valid test agent',
      capabilities: '["voice_call"]',
      walletAddress: 'invalid_address',
    }

    const result = agentSchema.safeParse(invalidData)
    expect(result.success).toBe(false)
  })
})
```

## Critical Testing Gaps

**No test framework installed:**
- Testing infrastructure needs to be set up
- Recommendation: Use vitest (recommended for Vite-based Next.js) or jest (if using current Next.js)

**Functions lacking test coverage:**
- `src/lib/auth.ts`: generateApiKey, validateApiKey, encryptApiKey, session management
- `src/lib/validators.ts`: All validation schemas and helper functions
- `src/app/api/agents/route.ts`: GET and POST handlers
- All React components in `src/components/`

**Critical paths to test first:**
1. Authentication flows (generateApiKey, validateApiKey, session tokens)
2. API key encryption/decryption (critical security)
3. Agent creation and validation
4. User authentication flows

## Setting Up Tests (Recommendations)

**Install test dependencies:**
```bash
pnpm add -D vitest @vitest/ui happy-dom @testing-library/react @testing-library/user-event
```

**Add to package.json:**
```json
{
  "scripts": {
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage"
  }
}
```

**Create vitest.config.ts:**
```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./vitest.setup.ts'],
  },
})
```

---

*Testing analysis: 2026-03-14*
