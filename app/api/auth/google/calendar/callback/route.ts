import { NextResponse } from 'next/server';
import { encryptApiKey } from '@/lib/auth';
import { prisma } from '@/lib/prisma';

/**
 * GET /api/auth/google/calendar/callback — Google OAuth callback.
 * Exchanges the authorization code for tokens, encrypts the refresh
 * token, and stores it in the user's profile for calendar access.
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get('code');
  const state = searchParams.get('state'); // userId
  const error = searchParams.get('error');

  if (error) {
    return NextResponse.redirect(`${origin}/?calendar=error&reason=${error}`);
  }

  if (!code || !state) {
    return NextResponse.redirect(`${origin}/?calendar=error&reason=missing_params`);
  }

  const clientId = process.env.GOOGLE_OAUTH_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_OAUTH_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    return NextResponse.redirect(`${origin}/?calendar=error&reason=not_configured`);
  }

  const redirectUri = `${origin}/api/auth/google/calendar/callback`;

  try {
    const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri,
        grant_type: 'authorization_code',
      }),
    });

    if (!tokenResponse.ok) {
      const errBody = await tokenResponse.text();
      console.error('Google token exchange failed:', errBody);
      return NextResponse.redirect(`${origin}/?calendar=error&reason=token_exchange`);
    }

    const tokens = await tokenResponse.json();

    const encryptedAccess = encryptApiKey(tokens.access_token);
    const encryptedRefresh = tokens.refresh_token
      ? encryptApiKey(tokens.refresh_token)
      : null;

    const userId = parseInt(state, 10);

    await prisma.user.update({
      where: { id: userId },
      data: {
        metadata: {
          googleCalendar: {
            accessToken: encryptedAccess,
            refreshToken: encryptedRefresh,
            expiresAt: Date.now() + (tokens.expires_in || 3600) * 1000,
            scope: tokens.scope,
            connectedAt: new Date().toISOString(),
          },
        },
      },
    });

    return NextResponse.redirect(`${origin}/?calendar=connected`);
  } catch (err) {
    console.error('Google Calendar OAuth callback error:', err);
    return NextResponse.redirect(`${origin}/?calendar=error&reason=internal`);
  }
}
