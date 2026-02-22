import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/src/lib/prisma';
import { hashPassword, createSessionToken } from '@/src/lib/auth';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { email, password, name } = body;

    if (!email || typeof email !== 'string' || !email.includes('@')) {
      return NextResponse.json({ error: 'Valid email is required' }, { status: 400 });
    }

    if (!password || typeof password !== 'string' || password.length < 6 || password.length > 1024) {
      return NextResponse.json({ error: 'Password must be between 6 and 1024 characters' }, { status: 400 });
    }

    const existing = await prisma.user.findUnique({ where: { email: email.toLowerCase() } });
    if (existing) {
      return NextResponse.json({ error: 'Email already registered' }, { status: 409 });
    }

    const user = await prisma.user.create({
      data: {
        email: email.toLowerCase(),
        passwordHash: hashPassword(password),
        name: name || null,
      },
    });

    const token = createSessionToken({ userId: user.id });

    return NextResponse.json(
      {
        user: { id: user.id, email: user.email, name: user.name },
        token,
      },
      { status: 201 },
    );
  } catch (error) {
    console.error('POST /api/auth/register error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
