import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getCurrentUser } from '@/lib/auth';
import { runVerification } from '@/lib/clawbot-verify';

export const maxDuration = 30;

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
