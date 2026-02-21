import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getCurrentUser } from '@/lib/auth';
import { agentSchema } from '@/lib/validators';

// GET /api/agents - List all agents, or only mine when ?mine=true
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const mine = url.searchParams.get('mine') === 'true';

    let ownerFilter: { ownerId?: number } = {};

    if (mine) {
      const user = await getCurrentUser(request);
      if (!user) {
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
      }
      ownerFilter = { ownerId: user.id };
    }

    const agents = await prisma.agent.findMany({
      where: ownerFilter,
      orderBy: { reputation: 'desc' },
      include: { owner: { select: { id: true, name: true } } },
    });

    return NextResponse.json({ agents });
  } catch (error) {
    console.error('Error fetching agents:', error);
    return NextResponse.json({ error: 'Failed to fetch agents' }, { status: 500 });
  }
}

// POST /api/agents - Register a new agent (requires auth)
export async function POST(request: Request) {
  try {
    const user = await getCurrentUser(request);
    
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const validation = agentSchema.safeParse(body);
    
    if (!validation.success) {
      return NextResponse.json({ 
        error: 'Validation failed', 
        details: validation.error.flatten() 
      }, { status: 400 });
    }

    const data = validation.data;

    // Zod validates URL format; additionally enforce HTTP(S) protocol
    if (data.apiEndpoint) {
      const protocol = new URL(data.apiEndpoint).protocol;
      if (protocol !== 'http:' && protocol !== 'https:') {
        return NextResponse.json({
          error: 'API endpoint must use HTTP or HTTPS protocol',
        }, { status: 400 });
      }
    }

    // Create the agent
    const agent = await prisma.agent.create({
      data: {
        title: data.title,
        description: data.description,
        category: data.category ?? null,
        priceUsd: data.priceUsd,
        tags: data.tags ?? null,
        network: data.network || 'solana-devnet',
        apiEndpoint: data.apiEndpoint ?? null,
        capabilities: data.capabilities ?? null,
        webhookUrl: data.webhookUrl ?? null,
        documentation: data.documentation ?? null,
        walletAddress: (body.walletAddress as string) || null,
        ownerId: user.id,
        status: 'pending',
        isVerified: false,
        minFeeUsdc: (body.minFeeUsdc as number) || 0.01,
        maxConcurrent: (body.maxConcurrent as number) || 5,
        bidAggressiveness: (body.bidAggressiveness as number) || 0.8,
        icon: body.icon || 'Bot',
      }
    });

    return NextResponse.json({ 
      success: true, 
      agent: {
        id: agent.id,
        title: agent.title,
        status: agent.status,
      },
      message: 'Agent registered successfully. Pending verification.'
    }, { status: 201 });

  } catch (error) {
    console.error('Error creating agent:', error);
    return NextResponse.json({ error: 'Failed to create agent' }, { status: 500 });
  }
}
