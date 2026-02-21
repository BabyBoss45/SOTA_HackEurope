import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/src/lib/prisma';

// POST /api/chat — save a message
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { sessionId, role, text, wallet } = body;

    if (!sessionId || !role || !text) {
      return NextResponse.json({ error: 'sessionId, role, and text are required' }, { status: 400 });
    }

    // Upsert session (create if not exists)
    // Pass title in update too so it gets set if the session was created
    // by an assistant message first (race condition → title was null).
    const candidateTitle = role === 'user' ? text.slice(0, 80) : undefined;
    await prisma.chatSession.upsert({
      where: { id: sessionId },
      update: { updatedAt: new Date(), ...(candidateTitle ? { title: candidateTitle } : {}) },
      create: { id: sessionId, wallet: wallet || null, title: candidateTitle ?? null },
    });

    // Create the message
    const message = await prisma.chatMessage.create({ data: { sessionId, role, text } });

    return NextResponse.json(message, { status: 201 });
  } catch (error) {
    console.error('POST /api/chat error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

// GET /api/chat?sessionId=xxx — load messages for a session
// GET /api/chat?wallet=xxx — list sessions for a wallet
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const sessionId = searchParams.get('sessionId');
    const wallet = searchParams.get('wallet');

    if (sessionId) {
      const messages = await prisma.chatMessage.findMany({
        where: { sessionId },
        orderBy: { createdAt: 'asc' },
      });
      return NextResponse.json(messages);
    }

    if (wallet) {
      const sessions = await prisma.chatSession.findMany({
        where: { wallet },
        orderBy: { updatedAt: 'desc' },
        take: 50,
      });
      return NextResponse.json(sessions);
    }

    // Return recent sessions if no filter
    const sessions = await prisma.chatSession.findMany({
      orderBy: { updatedAt: 'desc' },
      take: 20,
    });
    return NextResponse.json(sessions);
  } catch (error) {
    console.error('GET /api/chat error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
