import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getCurrentUser } from '@/lib/auth';

export const maxDuration = 30;

const BID_REQUEST_SCHEMA = {
  bidPrice: 'number',
  confidence: 'number',
  estimatedTimeSec: 'number',
  riskFactors: 'array',
};

function validateBidResponse(data: unknown): boolean {
  if (!data || typeof data !== 'object') return false;
  const d = data as Record<string, unknown>;
  if (typeof d.bidPrice !== 'number' || d.bidPrice < 0) return false;
  if (typeof d.confidence !== 'number' || d.confidence < 0 || d.confidence > 1) return false;
  if (typeof d.estimatedTimeSec !== 'number' || d.estimatedTimeSec <= 0) return false;
  if (!Array.isArray(d.riskFactors)) return false;
  return true;
}

async function runVerification(agentId: string, endpoint: string): Promise<void> {
  // Step 1: Health check (SDK's create_app() provides /health automatically)
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 5000);
    const healthRes = await fetch(`${endpoint}/health`, { signal: ctrl.signal });
    clearTimeout(timer);
    if (!healthRes.ok) throw new Error(`/health returned ${healthRes.status}`);
    const health = await healthRes.json();
    if (health?.status !== 'ok') throw new Error(`/health status not ok: ${JSON.stringify(health)}`);
  } catch (err) {
    console.warn(`[verify] Health check failed for ${agentId}:`, err);
    await prisma.externalAgent.update({
      where: { agentId },
      data: { status: 'suspended' },
    });
    return;
  }

  // Step 2: Test bid request (SDK agent handles this via register_routes + DefaultBidStrategy)
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 10000);
    const bidRes = await fetch(`${endpoint}/bid_request`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jobId: 'test-verification-000',
        description: 'Verification test job',
        tags: ['verification'],
        budgetUsdc: 0.01,
        metadata: { verification: true },
      }),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (!bidRes.ok) throw new Error(`/bid_request returned ${bidRes.status}`);
    const bidData = await bidRes.json();
    if (!validateBidResponse(bidData)) {
      throw new Error(`Invalid bid response schema: ${JSON.stringify(bidData)}`);
    }
    if ((bidData as Record<string, unknown>).bidPrice as number > 0.01) {
      throw new Error('Bid price exceeds test budget');
    }
  } catch (err) {
    console.warn(`[verify] Bid request test failed for ${agentId}:`, err);
    await prisma.externalAgent.update({
      where: { agentId },
      data: { status: 'suspended' },
    });
    return;
  }

  // All checks passed — activate
  await prisma.externalAgent.update({
    where: { agentId },
    data: { status: 'active', verifiedAt: new Date() },
  });
  console.log(`[verify] Agent ${agentId} verified and activated`);
}

type RouteContext = { params: Promise<{ agentId: string }> };

export async function POST(
  request: Request,
  { params }: RouteContext,
) {
  const { agentId } = await params;
  const user = await getCurrentUser(request);
  if (!user || user.role !== 'admin') {
    return NextResponse.json({ error: 'Admin access required' }, { status: 403 });
  }

  const agent = await prisma.externalAgent.findUnique({
    where: { agentId },
  });
  if (!agent) {
    return NextResponse.json({ error: 'Agent not found' }, { status: 404 });
  }
  if (agent.status === 'active') {
    return NextResponse.json({ success: true, status: 'already_active' });
  }

  // Mark as verifying, run checks in background
  await prisma.externalAgent.update({
    where: { agentId },
    data: { status: 'verifying' },
  });

  // Fire-and-forget background verification
  runVerification(agentId, agent.endpoint).catch((err) =>
    console.error(`[verify] Unexpected error for ${agentId}:`, err),
  );

  return NextResponse.json({ success: true, status: 'verification_started' });
}
