import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";

const BUTLER_API = process.env.BUTLER_API_URL;
if (!BUTLER_API) {
  console.error("BUTLER_API_URL not set");
}
const WEBHOOK_SECRET = process.env.INCIDENT_IO_WEBHOOK_SECRET || "";

// Svix signature verification (incident.io uses Svix for webhooks)
function verifySignature(
  payload: string,
  headers: {
    id: string | null;
    timestamp: string | null;
    signature: string | null;
  },
  secret: string,
): boolean {
  if (!secret || !headers.id || !headers.timestamp || !headers.signature) {
    return false;
  }

  const ts = headers.timestamp;
  const tolerance = 5 * 60; // 5 minutes
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(ts, 10)) > tolerance) {
    return false;
  }

  const toSign = `${headers.id}.${ts}.${payload}`;

  // Secret may be prefixed with "whsec_"
  const rawSecret = secret.startsWith("whsec_")
    ? Buffer.from(secret.slice(6), "base64")
    : Buffer.from(secret, "utf8");

  const expected = crypto
    .createHmac("sha256", rawSecret)
    .update(toSign)
    .digest("base64");

  const signatures = headers.signature.split(" ");
  return signatures.some((sig) => {
    const sigValue = sig.startsWith("v1,") ? sig.slice(3) : sig;
    try {
      return crypto.timingSafeEqual(
        Buffer.from(expected, "base64"),
        Buffer.from(sigValue, "base64"),
      );
    } catch {
      return false;
    }
  });
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.text();

    // Verify Svix signature if secret is configured
    if (WEBHOOK_SECRET) {
      const isValid = verifySignature(body, {
        id: req.headers.get("webhook-id"),
        timestamp: req.headers.get("webhook-timestamp"),
        signature: req.headers.get("webhook-signature"),
      }, WEBHOOK_SECRET);

      if (!isValid) {
        return NextResponse.json(
          { error: "Invalid signature" },
          { status: 401 },
        );
      }
    }

    const event = JSON.parse(body);
    const eventType: string = event.event_type || event.type || "";

    // Forward relevant events to Butler API for agent awareness
    if (
      BUTLER_API &&
      (eventType === "incident.updated" ||
      eventType === "incident.created")
    ) {
      const incident = event.data?.incident || event.incident || {};

      try {
        await fetch(`${BUTLER_API}/api/agent/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_id: incident.external_id || incident.id || "unknown",
            status: `incident_${eventType.split(".")[1]}`,
            message: `[incident.io] ${incident.name || "Incident"} — ${incident.incident_status?.name || "unknown status"}`,
            data: {
              incident_id: incident.id,
              severity: incident.severity?.name,
              status: incident.incident_status?.name,
              status_category: incident.incident_status?.category,
              permalink: incident.permalink,
              updated_at: incident.updated_at,
            },
            agent: "incident_io_webhook",
          }),
        });
      } catch (forwardErr) {
        console.error("Failed to forward incident event to Butler API:", forwardErr);
      }
    }

    return NextResponse.json({ received: true, event_type: eventType });
  } catch (err) {
    console.error("incident.io webhook error:", err);
    return NextResponse.json(
      { error: "Webhook processing failed" },
      { status: 500 },
    );
  }
}
