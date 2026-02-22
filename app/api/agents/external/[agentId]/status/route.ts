import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

type RouteContext = { params: Promise<{ agentId: string }> };

export async function GET(
  _request: Request,
  { params }: RouteContext,
) {
  const { agentId } = await params;

  const agent = await prisma.externalAgent.findUnique({
    where: { agentId },
    select: { agentId: true, name: true, status: true, verifiedAt: true },
  });

  if (!agent) {
    return NextResponse.json({ error: 'Agent not found' }, { status: 404 });
  }

  return NextResponse.json({
    agentId: agent.agentId,
    name: agent.name,
    status: agent.status,
    verifiedAt: agent.verifiedAt,
  });
}
