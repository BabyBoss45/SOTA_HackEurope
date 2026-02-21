import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { requireApiKeyAuth, AuthError } from '@/lib/auth';

// POST /api/marketplace/execute - Execute a job (called by marketplace when agent wins)
export async function POST(request: Request) {
  try {
    const { agent } = await requireApiKeyAuth(request, 'execute');

    const body = await request.json();
    const { jobId, result, status = 'completed' } = body;

    if (!jobId) {
      return NextResponse.json({ error: 'jobId is required' }, { status: 400 });
    }

    // Find the job
    const job = await prisma.marketplaceJob.findUnique({ where: { jobId } });

    if (!job) {
      return NextResponse.json({ error: 'Job not found' }, { status: 404 });
    }

    // Verify this agent is assigned to the job
    if (job.winner !== agent.title && job.status !== 'assigned') {
      return NextResponse.json({ error: 'Agent is not assigned to this job' }, { status: 403 });
    }

    // Update job status
    await prisma.marketplaceJob.update({
      where: { jobId },
      data: { status: status === 'completed' ? 'completed' : 'assigned' },
    });

    // Record the execution update
    await prisma.agentJobUpdate.create({
      data: {
        jobId: job.jobId,
        agent: agent.title,
        status,
        message: status === 'completed' ? 'Job completed successfully' : 'Job execution in progress',
        data: result || null,
      }
    });

    // Update agent stats
    const isSuccess = status === 'completed';
    await prisma.agent.update({
      where: { id: agent.id },
      data: {
        totalRequests: { increment: 1 },
        ...(isSuccess ? { successfulRequests: { increment: 1 } } : {}),
      },
    });

    // Notify developer via webhook (fire-and-forget)
    if (agent.webhookUrl) {
      fetch(agent.webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event: 'job.executed',
          jobId: job.jobId,
          agentId: agent.id,
          status,
          result,
          timestamp: new Date().toISOString(),
        }),
      }).catch(err => console.error('Webhook delivery failed:', err));
    }

    return NextResponse.json({
      success: true,
      execution: {
        jobId,
        agentId: agent.id,
        status,
      },
      message: 'Job execution recorded'
    });
  } catch (error) {
    if (error instanceof AuthError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    console.error('Error executing job:', error);
    return NextResponse.json({ error: 'Failed to execute job' }, { status: 500 });
  }
}
