import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getCurrentUser } from '@/lib/auth';

type RouteContext = { params: Promise<{ id: string }> };

function parseAgentId(id: string): number | null {
  const parsed = parseInt(id, 10);
  return isNaN(parsed) ? null : parsed;
}

// GET /api/agents/[id] - Get agent details
export async function GET(
  request: Request,
  { params }: RouteContext,
) {
  try {
    const agentId = parseAgentId((await params).id);
    if (!agentId) {
      return NextResponse.json({ error: 'Invalid agent ID' }, { status: 400 });
    }

    const agent = await prisma.agent.findUnique({
      where: { id: agentId },
      include: { owner: { select: { id: true, name: true } } },
    });

    if (!agent) {
      return NextResponse.json({ error: 'Agent not found' }, { status: 404 });
    }

    return NextResponse.json({ agent });
  } catch (error) {
    console.error('Error fetching agent:', error);
    return NextResponse.json({ error: 'Failed to fetch agent' }, { status: 500 });
  }
}

async function requireOwnedAgent(request: Request, params: RouteContext['params']): Promise<
  { agent: Awaited<ReturnType<typeof prisma.agent.findUnique>>; error?: never } |
  { agent?: never; error: ReturnType<typeof NextResponse.json> }
> {
  const user = await getCurrentUser(request);
  if (!user) {
    return { error: NextResponse.json({ error: 'Unauthorized' }, { status: 401 }) };
  }

  const agentId = parseAgentId((await params).id);
  if (!agentId) {
    return { error: NextResponse.json({ error: 'Invalid agent ID' }, { status: 400 }) };
  }

  const agent = await prisma.agent.findUnique({ where: { id: agentId } });
  if (!agent) {
    return { error: NextResponse.json({ error: 'Agent not found' }, { status: 404 }) };
  }

  if (agent.ownerId !== user.id) {
    return { error: NextResponse.json({ error: 'Forbidden' }, { status: 403 }) };
  }

  return { agent };
}

const UPDATABLE_FIELDS = [
  'title', 'description', 'category', 'tags', 'apiEndpoint',
  'capabilities', 'webhookUrl', 'documentation', 'minFeeUsdc',
  'maxConcurrent', 'bidAggressiveness', 'icon', 'walletAddress',
] as const;

// PATCH /api/agents/[id] - Update agent (owner only)
export async function PATCH(request: Request, { params }: RouteContext) {
  try {
    const result = await requireOwnedAgent(request, params);
    if (result.error) return result.error;

    const body = await request.json();
    const updateData: Record<string, unknown> = {};
    for (const field of UPDATABLE_FIELDS) {
      if (body[field] !== undefined) {
        updateData[field] = body[field];
      }
    }

    const agent = await prisma.agent.update({
      where: { id: result.agent!.id },
      data: updateData,
    });

    return NextResponse.json({
      success: true,
      agent: { id: agent.id, title: agent.title, status: agent.status },
    });
  } catch (error) {
    console.error('Error updating agent:', error);
    return NextResponse.json({ error: 'Failed to update agent' }, { status: 500 });
  }
}

// DELETE /api/agents/[id] - Delete agent (owner only)
export async function DELETE(request: Request, { params }: RouteContext) {
  try {
    const result = await requireOwnedAgent(request, params);
    if (result.error) return result.error;

    await prisma.agent.delete({ where: { id: result.agent!.id } });

    return NextResponse.json({ success: true, message: 'Agent deleted' });
  } catch (error) {
    console.error('Error deleting agent:', error);
    return NextResponse.json({ error: 'Failed to delete agent' }, { status: 500 });
  }
}
