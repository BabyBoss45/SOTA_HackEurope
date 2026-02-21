import { NextResponse } from 'next/server';
import { getCurrentUser } from '@/lib/auth';

const SCOPES = [
  'https://www.googleapis.com/auth/calendar.readonly',
  'https://www.googleapis.com/auth/calendar.freebusy',
];

/**
 * GET /api/auth/google/calendar — Initiate Google Calendar OAuth flow.
 * Redirects the user to Google's consent screen. After approval, Google
 * redirects back to /api/auth/google/calendar/callback with an auth code.
 */
export async function GET(request: Request) {
  const clientId = process.env.GOOGLE_OAUTH_CLIENT_ID;
  if (!clientId) {
    return NextResponse.json(
      { error: 'Google Calendar integration not configured' },
      { status: 503 },
    );
  }

  const user = await getCurrentUser(request);
  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { origin } = new URL(request.url);
  const redirectUri = `${origin}/api/auth/google/calendar/callback`;

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: SCOPES.join(' '),
    access_type: 'offline',
    prompt: 'consent',
    state: String(user.id),
  });

  return NextResponse.redirect(
    `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`,
  );
}
