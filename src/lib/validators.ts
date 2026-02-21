import { z } from "zod";

// ── Shared validation helpers ────────────────────────────────────────────────
// Single source of truth — import these in frontend pages instead of duplicating

const SOLANA_ADDRESS_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

/** Validate a base-58 Solana address (regex, no checksum). */
export function isValidSolanaAddress(addr: string): boolean {
  return SOLANA_ADDRESS_RE.test(addr);
}

/** Validate an HTTP(S) URL string. */
export function isValidHttpUrl(s: string): boolean {
  try {
    const u = new URL(s);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

/** Shared category options used across all agent forms. */
export const AGENT_CATEGORIES = [
  { value: "automation", label: "Automation" },
  { value: "data", label: "Data & Analytics" },
  { value: "communication", label: "Communication" },
  { value: "blockchain", label: "Blockchain" },
  { value: "other", label: "Other" },
] as const;

/** Safely parse a JSON-encoded capabilities string. Returns string[] or fallback. */
export function parseCapabilities(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

// ── Zod helper: optional string that treats "" as undefined ──────────────────
const optionalString = z
  .string()
  .transform((v) => (v.trim() === "" ? undefined : v))
  .pipe(z.string().optional());

const optionalUrl = z
  .string()
  .transform((v) => (v.trim() === "" ? undefined : v))
  .pipe(z.string().url().optional());

const optionalSolanaAddress = z
  .string()
  .transform((v) => (v.trim() === "" ? undefined : v))
  .pipe(
    z
      .string()
      .regex(SOLANA_ADDRESS_RE, "Must be a valid Solana address")
      .optional()
  );

// ── Schemas ──────────────────────────────────────────────────────────────────

export const authSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6, "Password must be at least 6 characters"),
  name: z.string().min(2, "Name is required").optional(),
});

export const agentSchema = z.object({
  title: z.string().min(3),
  description: z.string().min(10),
  category: optionalString,
  priceUsd: z.number().min(0).optional(),
  tags: optionalString,
  network: optionalString,
  // Developer portal fields
  apiEndpoint: optionalUrl,
  apiKey: optionalString,
  capabilities: z.string().refine(
    (val) => {
      try {
        const arr = JSON.parse(val);
        return Array.isArray(arr) && arr.length >= 1;
      } catch {
        return false;
      }
    },
    { message: "At least 1 capability is required" }
  ),
  webhookUrl: optionalUrl,
  documentation: optionalString,
  // Wallet & pricing
  walletAddress: optionalSolanaAddress,
  minFeeUsdc: z.number().min(0).optional(),
  // Bidding & concurrency
  bidAggressiveness: z.number().min(0.5).max(1.0).optional(),
  maxConcurrent: z.number().int().min(1).max(100).optional(),
  icon: optionalString,
});

/** Partial schema for PATCH updates — every field optional, same validation rules. */
export const agentUpdateSchema = z.object({
  title: z.string().min(3).optional(),
  description: z.string().min(10).optional(),
  category: optionalString,
  tags: optionalString,
  apiEndpoint: optionalUrl,
  capabilities: z
    .string()
    .refine(
      (val) => {
        try {
          const arr = JSON.parse(val);
          return Array.isArray(arr) && arr.length >= 1;
        } catch {
          return false;
        }
      },
      { message: "At least 1 capability is required" }
    )
    .optional(),
  webhookUrl: optionalUrl,
  documentation: optionalString,
  walletAddress: optionalSolanaAddress,
  minFeeUsdc: z.number().min(0).optional(),
  maxConcurrent: z.number().int().min(1).max(100).optional(),
  bidAggressiveness: z.number().min(0.5).max(1.0).optional(),
  icon: optionalString,
});

export const profileSchema = z.object({
  walletAddress: optionalSolanaAddress,
  name: z.string().min(2).optional(),
});

export type AuthPayload = z.infer<typeof authSchema>;
export type AgentPayload = z.infer<typeof agentSchema>;
export type AgentUpdatePayload = z.infer<typeof agentUpdateSchema>;
export type ProfilePayload = z.infer<typeof profileSchema>;
