import { NextResponse } from 'next/server';
import { z } from 'zod';
import { createHmac, timingSafeEqual } from 'crypto';
import { prisma } from '@/lib/prisma';
import { decryptApiKey } from '@/lib/auth';

const BUTLER_API_URL = process.env.BUTLER_API_URL ?? '';
const INTERNAL_API_SECRET = process.env.INTERNAL_API_SECRET ?? '';
const MAX_EXECUTION_MS = 300_000;
const HMAC_TOLERANCE_SECONDS = 300;

const executionResultSchema = z.object({
  success: z.boolean(),
  failure_type: z
    .enum(['captcha', 'timeout', 'blocked', 'not_found', 'auth_error', 'other'])
    .optional(),
  execution_time_ms: z.number().int().min(0).max(MAX_EXECUTION_MS),
  proof: z.unknown().optional(),
});

const bodySchema = z.object({
  jobId: z.string().min(1),
  executionToken: z.string().uuid(),
  result: executionResultSchema,
});

function verifyHMACSignature(
  payload: object,
  signatureHeader: string,
  keyHex: string,
): boolean {
  try {
    const parts = Object.fromEntries(
      signatureHeader.split(',').map((p) => p.split('=') as [string, string]),
    );
    const ts = parseInt(parts['t'] ?? '0', 10);
    const receivedSig = parts['v1'] ?? '';
    if (Math.abs(Date.now() / 1000 - ts) > HMAC_TOLERANCE_SECONDS) return false;

    const sortedKeys = Object.keys(payload).sort();
    const body = JSON.stringify(payload, sortedKeys);
    const message = `${ts}.${body}`;
    const key = Buffer.from(keyHex, 'hex');
    const expected = createHmac('sha256', key).update(message).digest('hex');

    return timingSafeEqual(Buffer.from(expected, 'hex'), Buffer.from(receivedSig, 'hex'));
  } catch {
    return false;
  }
}

function validateProofDomains(proof: unknown, supportedDomains: string[]): boolean {
  if (!proof) return true;
  const proofStr = JSON.stringify(proof);
  const urlPattern = /https?:\/\/([^/\s"]+)/g;
  let match: RegExpExecArray | null;
  while ((match = urlPattern.exec(proofStr)) !== null) {
    const host = match[1].toLowerCase();
    const allowed = supportedDomains.some(
      (d) => host === d.toLowerCase() || host.endsWith('.' + d.toLowerCase()),
    );
    if (!allowed) return false;
  }
  return true;
}

async function triggerEscrowRelease(jobId: string, walletAddress: string): Promise<void> {
  if (!INTERNAL_API_SECRET) return;
  try {
    await fetch(`${BUTLER_API_URL}/internal/release-payment`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-Secret': INTERNAL_API_SECRET,
      },
      body: JSON.stringify({ job_id: jobId, wallet_address: walletAddress }),
    });
  } catch (err) {
    console.error('[external/execute] Escrow release failed:', err);
  }
}

async function triggerEscrowRefund(jobId: string): Promise<void> {
  if (!INTERNAL_API_SECRET) return;
  try {
    await fetch(`${BUTLER_API_URL}/internal/refund-escrow`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-Secret': INTERNAL_API_SECRET,
      },
      body: JSON.stringify({ job_id: jobId }),
    });
  } catch (err) {
    console.error('[external/execute] Escrow refund failed:', err);
  }
}

function updateReputationAsync(
  agentId: string,
  success: boolean,
  executionTimeMs: number,
  confidenceSubmitted: number | null,
  failureType: string | undefined,
): void {
  // Fire-and-forget reputation upsert
  (async () => {
    try {
      const existing = await prisma.externalAgentReputation.findUnique({
        where: { agentId },
      });

      const prevTotal = existing?.totalJobs ?? 0;
      const prevSuccessful = existing?.successfulJobs ?? 0;
      const prevFailed = existing?.failedJobs ?? 0;
      const prevAvgMs = existing?.avgExecutionTimeMs ?? 0;
      const prevDisputes = existing?.disputes ?? 0;
      const newTotal = prevTotal + 1;
      const newSuccessful = prevSuccessful + (success ? 1 : 0);
      const newFailed = prevFailed + (success ? 0 : 1);
      const newAvgMs =
        prevTotal === 0
          ? executionTimeMs
          : (prevAvgMs * prevTotal + executionTimeMs) / newTotal;

      // Update failureTypes JSON
      const prevTypes =
        (existing?.failureTypes as Record<string, number> | null) ?? {};
      const newTypes = { ...prevTypes };
      if (!success && failureType) {
        newTypes[failureType] = (newTypes[failureType] ?? 0) + 1;
      }

      // Compute reputation score
      const successRate = newSuccessful / newTotal;
      const speedFactor = Math.max(0, 1 - newAvgMs / 120_000);
      const lowDisputeFactor = Math.max(
        0,
        1 - prevDisputes / Math.max(newTotal, 1),
      );
      const reputationScore = Math.min(
        1,
        Math.max(
          0,
          successRate * 0.6 + speedFactor * 0.2 + lowDisputeFactor * 0.2,
        ),
      );

      // Confidence error delta
      let avgConfidenceError = existing?.avgConfidenceError ?? 0;
      if (confidenceSubmitted !== null) {
        const actual = success ? 1 : 0;
        const delta = Math.abs(confidenceSubmitted - actual);
        avgConfidenceError =
          prevTotal === 0
            ? delta
            : (avgConfidenceError * prevTotal + delta) / newTotal;
      }

      await prisma.externalAgentReputation.upsert({
        where: { agentId },
        create: {
          agentId,
          totalJobs: newTotal,
          successfulJobs: newSuccessful,
          failedJobs: newFailed,
          avgExecutionTimeMs: newAvgMs,
          avgConfidenceError,
          failureTypes: newTypes,
          reputationScore,
        },
        update: {
          totalJobs: newTotal,
          successfulJobs: newSuccessful,
          failedJobs: newFailed,
          avgExecutionTimeMs: newAvgMs,
          avgConfidenceError,
          failureTypes: newTypes,
          reputationScore,
        },
      });
    } catch (err) {
      console.error('[external/execute] Reputation update failed:', err);
    }
  })();
}

export async function POST(request: Request) {
  let body: z.infer<typeof bodySchema>;
  try {
    const raw = await request.json();
    const parsed = bodySchema.safeParse(raw);
    if (!parsed.success) {
      return NextResponse.json(
        { error: 'Invalid payload', details: parsed.error.flatten().fieldErrors },
        { status: 400 },
      );
    }
    body = parsed.data;
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  // Atomic token consumption — prevents replay attacks
  const now = new Date();
  const consumed = await prisma.$queryRaw<Array<{ id: number; agentId: string; confidenceSubmitted: number | null }>>`
    UPDATE "ExecutionToken"
    SET used = TRUE, "usedAt" = ${now}
    WHERE token = ${body.executionToken}
      AND "jobId" = ${body.jobId}
      AND used = FALSE
      AND "expiresAt" > ${now}
    RETURNING id, "agentId", "confidenceSubmitted"
  `;

  if (!consumed.length) {
    // Distinguish the failure reason
    const existing = await prisma.executionToken.findFirst({
      where: { token: body.executionToken },
    });
    if (!existing) return NextResponse.json({ error: 'Token not found' }, { status: 401 });
    if (existing.used) return NextResponse.json({ error: 'Token already used' }, { status: 401 });
    return NextResponse.json({ error: 'Token expired' }, { status: 401 });
  }

  const { agentId, confidenceSubmitted } = consumed[0];

  // Load external agent
  const agent = await prisma.externalAgent.findUnique({
    where: { agentId },
  });
  if (!agent || agent.status !== 'active') {
    return NextResponse.json({ error: 'Agent not active' }, { status: 403 });
  }

  // HMAC signature validation (if agent has a signing key)
  if (agent.publicKey) {
    const sigHeader = request.headers.get('X-SOTA-Signature');
    if (!sigHeader) {
      return NextResponse.json({ error: 'Missing X-SOTA-Signature' }, { status: 401 });
    }
    try {
      const keyHex = decryptApiKey(agent.publicKey);
      // Re-read body for signature verification (payload is the full request body)
      const isValid = verifyHMACSignature(
        { jobId: body.jobId, executionToken: body.executionToken, result: body.result },
        sigHeader,
        keyHex,
      );
      if (!isValid) {
        return NextResponse.json({ error: 'Invalid signature' }, { status: 401 });
      }
    } catch (err) {
      console.error('[external/execute] HMAC verification error:', err);
      return NextResponse.json({ error: 'Signature verification failed' }, { status: 401 });
    }
  }

  // Enforce execution time cap
  const result = body.result;
  const effectiveSuccess =
    result.success && result.execution_time_ms <= MAX_EXECUTION_MS;
  const effectiveFailureType =
    !effectiveSuccess && result.execution_time_ms > MAX_EXECUTION_MS
      ? 'timeout'
      : result.failure_type;

  // Domain allowlist validation
  if (effectiveSuccess && !validateProofDomains(result.proof, agent.supportedDomains)) {
    console.warn(`[external/execute] Agent ${agentId} proof references unsupported domain`);
    // Don't block payment on this, but log for audit
  }

  // Update job status
  try {
    await prisma.marketplaceJob.update({
      where: { jobId: body.jobId },
      data: {
        status: effectiveSuccess ? 'completed' : 'assigned',
        ...(effectiveSuccess ? { winner: `external:${agent.name}` } : {}),
      },
    });
  } catch {
    // Job may not exist in this DB (could be from in-memory board only) — continue
  }

  // Record the execution update
  await prisma.agentJobUpdate.create({
    data: {
      jobId: body.jobId,
      agent: `external:${agent.name}`,
      status: effectiveSuccess ? 'completed' : 'error',
      message: effectiveSuccess
        ? `Executed in ${result.execution_time_ms}ms`
        : `Failed: ${effectiveFailureType ?? 'unknown'}`,
      data: {
        externalAgentId: agentId,
        success: effectiveSuccess,
        executionTimeMs: result.execution_time_ms,
        failureType: effectiveFailureType ?? null,
        proof: (result.proof as import('@prisma/client').Prisma.InputJsonValue) ?? null,
      },
    },
  });

  // Trigger escrow action
  if (effectiveSuccess) {
    triggerEscrowRelease(body.jobId, agent.walletAddress);
  } else {
    triggerEscrowRefund(body.jobId);
  }

  // Update reputation (fire-and-forget)
  updateReputationAsync(
    agentId,
    effectiveSuccess,
    result.execution_time_ms,
    confidenceSubmitted,
    effectiveFailureType,
  );

  return NextResponse.json({ received: true, success: effectiveSuccess });
}
