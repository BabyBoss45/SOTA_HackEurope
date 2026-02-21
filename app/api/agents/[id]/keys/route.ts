import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getCurrentUser, generateApiKey } from '@/lib/auth';

type RouteContext = { params: Promise<{ id: string }> };

function parseAgentId(id: string): number | null {
  const parsed = parseInt(id, 10);
  return isNaN(parsed) ? null : parsed;
}

async function requireOwnedAgent(request: Request, params: RouteContext['params']): Promise<
  { agentId: number; error?: never } |
  { agentId?: never; error: ReturnType<typeof NextResponse.json> }
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

  return { agentId };
}

// GET /api/agents/[id]/keys - List API keys for an agent
export async function GET(request: Request, { params }: RouteContext) {
  try {
    const result = await requireOwnedAgent(request, params);
    if (result.error) return result.error;

    const keys = await prisma.agentApiKey.findMany({
      where: { agentId: result.agentId },
      orderBy: { createdAt: 'desc' },
      select: {
        id: true,
        keyId: true,
        name: true,
        permissions: true,
        lastUsedAt: true,
        expiresAt: true,
        isActive: true,
        createdAt: true,
      },
    });

    return NextResponse.json({ keys });
  } catch (error) {
    console.error('Error fetching API keys:', error);
    return NextResponse.json({ error: 'Failed to fetch API keys' }, { status: 500 });
  }
}

// POST /api/agents/[id]/keys - Create a new API key
export async function POST(request: Request, { params }: RouteContext) {
  try {
    const result = await requireOwnedAgent(request, params);
    if (result.error) return result.error;

    const body = await request.json();
    const { name = 'Default', permissions = ['execute', 'bid'], expiresInDays } = body;

    const { keyId, fullKey, keyHash } = generateApiKey();

    const expiresAt = typeof expiresInDays === 'number'
      ? new Date(Date.now() + expiresInDays * 24 * 60 * 60 * 1000)
      : null;

    await prisma.agentApiKey.create({
      data: {
        keyId,
        keyHash,
        agentId: result.agentId,
        name,
        permissions,
        expiresAt,
      },
    });

    // Return the full key -- this is the ONLY time it will be shown
    return NextResponse.json({
      success: true,
      apiKey: { keyId, fullKey, name, permissions, expiresAt },
      message: 'API key created. Save this key securely - it will not be shown again.',
    }, { status: 201 });
  } catch (error) {
    console.error('Error creating API key:', error);
    return NextResponse.json({ error: 'Failed to create API key' }, { status: 500 });
  }
}

// DELETE /api/agents/[id]/keys - Revoke an API key
export async function DELETE(request: Request, { params }: RouteContext) {
  try {
    const result = await requireOwnedAgent(request, params);
    if (result.error) return result.error;

    const { keyId } = await request.json();
    if (!keyId) {
      return NextResponse.json({ error: 'keyId is required' }, { status: 400 });
    }

    const updated = await prisma.agentApiKey.updateMany({
      where: { keyId, agentId: result.agentId },
      data: { isActive: false },
    });

    if (updated.count === 0) {
      return NextResponse.json({ error: 'API key not found' }, { status: 404 });
    }

    return NextResponse.json({ success: true, message: 'API key revoked' });
  } catch (error) {
    console.error('Error revoking API key:', error);
    return NextResponse.json({ error: 'Failed to revoke API key' }, { status: 500 });
  }
}
