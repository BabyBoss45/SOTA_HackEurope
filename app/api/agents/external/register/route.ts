import { NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@/lib/prisma';
import { encryptApiKey } from '@/lib/auth';
import { runVerification } from '@/lib/clawbot-verify';

// Rate limiting: 5 registrations per IP per hour
const _rateLimiter = new Map<string, { count: number; resetAt: number }>();

function checkRateLimit(ip: string): boolean {
  const now = Date.now();
  const entry = _rateLimiter.get(ip);
  if (!entry || now > entry.resetAt) {
    _rateLimiter.set(ip, { count: 1, resetAt: now + 3600_000 });
    return true;
  }
  if (entry.count >= 5) return false;
  entry.count++;
  return true;
}

const registrationSchema = z.object({
  name: z.string().min(3).max(100),
  description: z.string().min(10).max(2000),
  endpoint: z
    .string()
    .url()
    .refine((u) => u.startsWith('https://'), { message: 'Endpoint must use HTTPS' }),
  capabilities: z.array(z.string().min(1)).min(1).max(50),
  supportedDomains: z.array(z.string().min(1)).min(1).max(50),
  // Solana base58 address: 32–44 chars
  walletAddress: z
    .string()
    .regex(/^[1-9A-HJ-NP-Za-km-z]{32,44}$/, { message: 'Invalid Solana wallet address' }),
  publicKey: z.string().min(32).optional(),
});

export async function POST(request: Request) {
  try {
    // Rate limit by IP
    const ip =
      request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ?? 'unknown';
    if (!checkRateLimit(ip)) {
      return NextResponse.json(
        { error: 'Too many registrations — try again in an hour' },
        { status: 429 },
      );
    }

    const body = await request.json();
    const parsed = registrationSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: 'Validation failed', details: parsed.error.flatten().fieldErrors },
        { status: 400 },
      );
    }

    const data = parsed.data;

    // Encrypt the HMAC signing key before storing
    const encryptedPublicKey = data.publicKey ? encryptApiKey(data.publicKey) : undefined;

    const agent = await prisma.externalAgent.create({
      data: {
        name: data.name,
        description: data.description,
        endpoint: data.endpoint,
        capabilities: data.capabilities.map((c) => c.toLowerCase()),
        supportedDomains: data.supportedDomains.map((d) => d.toLowerCase()),
        walletAddress: data.walletAddress,
        ...(encryptedPublicKey ? { publicKey: encryptedPublicKey } : {}),
        status: 'pending',
      },
    });

    // Auto-verify: run health + bid checks in background (no admin needed)
    runVerification(agent.agentId, data.endpoint).catch((err) =>
      console.error(`[register] Auto-verification failed for ${agent.agentId}:`, err),
    );

    return NextResponse.json({
      success: true,
      agentId: agent.agentId,
      status: 'pending',
      message:
        'ClawBot registered. Verification running — your agent will be active within seconds if health and bid checks pass. Poll /api/agents/external/{agentId}/status to check.',
    });
  } catch (err) {
    console.error('External agent registration error:', err);
    return NextResponse.json({ error: 'Registration failed' }, { status: 500 });
  }
}
