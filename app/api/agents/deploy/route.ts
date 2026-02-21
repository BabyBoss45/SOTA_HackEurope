import { NextResponse } from 'next/server';
import { getCurrentUser } from '@/lib/auth';
import { z } from 'zod';
import JSZip from 'jszip';
import {
  generateAgentPy,
  generateEnv,
  generateDockerfile,
  generateDockerignore,
  generateRequirements,
  generateReadme,
  sanitiseName,
  type AgentTemplateConfig,
} from '@/lib/agent-templates';

// ---------------------------------------------------------------------------
// Input validation schema
// ---------------------------------------------------------------------------

const deploySchema = z.object({
  name: z
    .string()
    .min(2, 'Agent name must be at least 2 characters')
    .max(64, 'Agent name must be at most 64 characters')
    .regex(/^[a-zA-Z0-9][a-zA-Z0-9_-]*$/, 'Name must start with a letter or number and contain only letters, numbers, hyphens, and underscores'),
  description: z
    .string()
    .min(10, 'Description must be at least 10 characters')
    .max(500, 'Description must be at most 500 characters'),
  tags: z.array(z.string().max(32)).max(20).default([]),
  capabilities: z.array(z.string().max(32)).max(20).default([]),
  priceRatio: z.number().min(0.5).max(1.0).default(0.8),
  minFeeUsdc: z.number().min(0).max(10000).default(0.5),
  walletAddress: z.string().max(128).default(''),
  hubUrl: z.string().max(256).default(process.env.NEXT_PUBLIC_HUB_WS_URL || 'ws://localhost:3002/ws/agent'),
  chain: z.enum(['solana-devnet', 'solana-mainnet']).default('solana-devnet'),
});

// ---------------------------------------------------------------------------
// POST /api/agents/deploy — Generate project ZIP
// ---------------------------------------------------------------------------

export async function POST(request: Request) {
  try {
    const user = await getCurrentUser(request);
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const validation = deploySchema.safeParse(body);

    if (!validation.success) {
      return NextResponse.json(
        { error: 'Validation failed', details: validation.error.flatten() },
        { status: 400 },
      );
    }

    const data = validation.data;
    const config: AgentTemplateConfig = {
      name: data.name,
      description: data.description,
      tags: data.tags,
      capabilities: data.capabilities,
      priceRatio: data.priceRatio,
      minFeeUsdc: data.minFeeUsdc,
      walletAddress: data.walletAddress,
      hubUrl: data.hubUrl,
      chain: data.chain,
    };

    const safeName = sanitiseName(config.name);

    // Build ZIP
    const zip = new JSZip();
    const folder = zip.folder(safeName)!;

    folder.file('agent.py', generateAgentPy(config));
    folder.file('.env.example', generateEnv(config));
    folder.file('requirements.txt', generateRequirements());
    folder.file('Dockerfile', generateDockerfile());
    folder.file('.dockerignore', generateDockerignore());
    folder.file('README.md', generateReadme(config));

    const zipArrayBuffer = await zip.generateAsync({ type: 'arraybuffer' });

    return new Response(zipArrayBuffer, {
      status: 200,
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition': `attachment; filename="${safeName}-agent.zip"`,
      },
    });
  } catch (error) {
    console.error('Deploy ZIP generation error:', error);
    return NextResponse.json(
      { error: 'Failed to generate project ZIP' },
      { status: 500 },
    );
  }
}
