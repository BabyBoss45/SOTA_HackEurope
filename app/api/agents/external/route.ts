import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function GET() {
  try {
    const agents = await prisma.externalAgent.findMany({
      include: { reputation: true },
      orderBy: { createdAt: 'desc' },
    });
    return NextResponse.json({ agents });
  } catch {
    return NextResponse.json({ agents: [] });
  }
}
