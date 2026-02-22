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
    include: { reputation: true },
  });

  if (!agent) {
    return NextResponse.json({ error: 'Agent not found' }, { status: 404 });
  }

  // Fetch last 20 job updates attributed to this external agent
  const recentUpdates = await prisma.agentJobUpdate.findMany({
    where: {
      data: {
        path: ['externalAgentId'],
        equals: agentId,
      },
    },
    orderBy: { createdAt: 'desc' },
    take: 20,
  });

  const rep = agent.reputation;
  const successRate =
    rep && rep.totalJobs > 0 ? rep.successfulJobs / rep.totalJobs : null;

  return NextResponse.json({
    agentId: agent.agentId,
    name: agent.name,
    status: agent.status,
    capabilities: agent.capabilities,
    supportedDomains: agent.supportedDomains,
    verifiedAt: agent.verifiedAt,
    reputation: rep
      ? {
          score: rep.reputationScore,
          totalJobs: rep.totalJobs,
          successfulJobs: rep.successfulJobs,
          failedJobs: rep.failedJobs,
          successRate,
          avgExecutionTimeMs: rep.avgExecutionTimeMs,
          avgConfidenceError: rep.avgConfidenceError,
          disputes: rep.disputes,
          failureTypes: rep.failureTypes,
          updatedAt: rep.updatedAt,
        }
      : null,
    recentJobs: recentUpdates.map((u) => ({
      jobId: u.jobId,
      status: u.status,
      message: u.message,
      data: u.data,
      createdAt: u.createdAt,
    })),
  });
}
