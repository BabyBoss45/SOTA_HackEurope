import { NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@/lib/prisma';
import { getCurrentUser } from '@/lib/auth';

const BUTLER_API_URL = process.env.BUTLER_API_URL ?? '';
const INTERNAL_API_SECRET = process.env.INTERNAL_API_SECRET ?? '';

const createDisputeSchema = z.object({
  jobId: z.string().min(1),
  agentId: z.string().uuid(),
  reason: z.string().min(10).max(2000),
});

async function triggerEscrowRelease(jobId: string, walletAddress: string): Promise<void> {
  if (!INTERNAL_API_SECRET) return;
  try {
    await fetch(`${BUTLER_API_URL}/internal/release-payment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Internal-Secret': INTERNAL_API_SECRET },
      body: JSON.stringify({ job_id: jobId, wallet_address: walletAddress }),
    });
  } catch (err) {
    console.error('[disputes] Escrow release failed:', err);
  }
}

async function triggerEscrowRefund(jobId: string): Promise<void> {
  if (!INTERNAL_API_SECRET) return;
  try {
    await fetch(`${BUTLER_API_URL}/internal/refund-escrow`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Internal-Secret': INTERNAL_API_SECRET },
      body: JSON.stringify({ job_id: jobId }),
    });
  } catch (err) {
    console.error('[disputes] Escrow refund failed:', err);
  }
}

async function autoResolveDispute(disputeId: number): Promise<void> {
  const REPUTATION_THRESHOLD = 0.75;
  try {
    const dispute = await prisma.dispute.findUnique({ where: { id: disputeId } });
    if (!dispute) return;

    const rep = await prisma.externalAgentReputation.findUnique({
      where: { agentId: dispute.agentId },
    });
    const score = rep?.reputationScore ?? 0;

    if (score >= REPUTATION_THRESHOLD) {
      // High reputation: favour the agent
      const agent = await prisma.externalAgent.findUnique({
        where: { agentId: dispute.agentId },
      });
      await prisma.dispute.update({
        where: { id: disputeId },
        data: {
          status: 'resolved',
          resolution: `Auto-resolved in favour of agent (reputation score ${score.toFixed(2)} ≥ ${REPUTATION_THRESHOLD})`,
          resolvedAt: new Date(),
        },
      });
      if (agent) await triggerEscrowRelease(dispute.jobId, agent.walletAddress);
    } else {
      // Low reputation: refund user
      await prisma.dispute.update({
        where: { id: disputeId },
        data: {
          status: 'resolved',
          resolution: `Auto-refunded (agent reputation score ${score.toFixed(2)} < ${REPUTATION_THRESHOLD})`,
          resolvedAt: new Date(),
        },
      });
      await triggerEscrowRefund(dispute.jobId);
    }

    // Increment dispute counter on agent reputation
    await prisma.externalAgentReputation.upsert({
      where: { agentId: dispute.agentId },
      create: { agentId: dispute.agentId, disputes: 1 },
      update: { disputes: { increment: 1 } },
    });
  } catch (err) {
    console.error('[disputes] Auto-resolve failed:', err);
  }
}

// POST /api/disputes — raise a dispute (job poster only)
export async function POST(request: Request) {
  const user = await getCurrentUser(request);
  if (!user) {
    return NextResponse.json({ error: 'Authentication required' }, { status: 401 });
  }

  const body = await request.json().catch(() => null);
  const parsed = createDisputeSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: 'Validation failed', details: parsed.error.flatten().fieldErrors },
      { status: 400 },
    );
  }

  const { jobId, agentId, reason } = parsed.data;

  // Verify job exists and caller is the poster
  const job = await prisma.marketplaceJob.findUnique({ where: { jobId } });
  if (!job) return NextResponse.json({ error: 'Job not found' }, { status: 404 });
  if (job.poster && user.walletAddress && job.poster !== user.walletAddress) {
    return NextResponse.json({ error: 'Only the job poster can raise a dispute' }, { status: 403 });
  }
  if (job.status !== 'completed') {
    return NextResponse.json(
      { error: `Cannot dispute a job in status: ${job.status}` },
      { status: 400 },
    );
  }

  // Check no open dispute already exists
  const existing = await prisma.dispute.findFirst({
    where: { jobId, status: 'open' },
  });
  if (existing) {
    return NextResponse.json(
      { error: 'An open dispute already exists for this job' },
      { status: 409 },
    );
  }

  // Create dispute and freeze payment by setting job status to 'disputed'
  const dispute = await prisma.dispute.create({
    data: {
      jobId,
      raisedBy: user.walletAddress ?? user.email,
      agentId,
      reason,
    },
  });

  await prisma.marketplaceJob.update({
    where: { jobId },
    data: { status: 'disputed' },
  });

  // Auto-resolve asynchronously
  autoResolveDispute(dispute.id).catch((err) =>
    console.error('[disputes] Auto-resolve threw:', err),
  );

  return NextResponse.json({ success: true, disputeId: dispute.id });
}

// GET /api/disputes — list disputes (admin) or by jobId (poster)
export async function GET(request: Request) {
  const user = await getCurrentUser(request);
  if (!user) {
    return NextResponse.json({ error: 'Authentication required' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const jobId = searchParams.get('jobId');

  if (user.role === 'admin') {
    const disputes = await prisma.dispute.findMany({
      where: jobId ? { jobId } : undefined,
      orderBy: { createdAt: 'desc' },
      take: 50,
    });
    return NextResponse.json({ disputes });
  }

  // Non-admin: only show disputes for their own jobs
  if (!jobId) {
    return NextResponse.json({ error: 'jobId query parameter required' }, { status: 400 });
  }
  const job = await prisma.marketplaceJob.findUnique({ where: { jobId } });
  if (!job || (job.poster && user.walletAddress && job.poster !== user.walletAddress)) {
    return NextResponse.json({ error: 'Access denied' }, { status: 403 });
  }

  const disputes = await prisma.dispute.findMany({
    where: { jobId },
    orderBy: { createdAt: 'desc' },
  });
  return NextResponse.json({ disputes });
}
