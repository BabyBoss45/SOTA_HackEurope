import { NextRequest, NextResponse } from "next/server";

/* ── Simple in-memory rate limiter (per IP, 10 req/min) ── */
const WINDOW_MS = 60_000;
const MAX_REQUESTS = 10;
const hits = new Map<string, number[]>();

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const timestamps = (hits.get(ip) || []).filter((t) => now - t < WINDOW_MS);
  if (timestamps.length >= MAX_REQUESTS) return true;
  timestamps.push(now);
  hits.set(ip, timestamps);
  return false;
}

export async function GET(req: NextRequest) {
  /* ── Rate limit by IP ── */
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
  if (isRateLimited(ip)) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429 });
  }

  const agentId = process.env.ELEVENLABS_AGENT_ID;
  const apiKey = process.env.ELEVENLABS_API_KEY;

  if (!agentId || !apiKey) {
    return NextResponse.json(
      { error: "Missing ElevenLabs configuration" },
      { status: 500 }
    );
  }

  const res = await fetch(
    `https://api.elevenlabs.io/v1/convai/conversation/token?agent_id=${agentId}`,
    { headers: { "xi-api-key": apiKey } }
  );

  if (!res.ok) {
    console.error("ElevenLabs token error:", await res.text().catch(() => res.statusText));
    return NextResponse.json(
      { error: "Failed to generate conversation token" },
      { status: 502 }
    );
  }

  const data = await res.json();
  if (!data.token || typeof data.token !== "string") {
    return NextResponse.json(
      { error: "Invalid token response from ElevenLabs" },
      { status: 502 }
    );
  }

  return NextResponse.json({ token: data.token });
}
