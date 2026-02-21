import { PublicKey } from "@solana/web3.js";

// ── Solana RPC endpoint ─────────────────────────────────────
export const SOLANA_RPC_URL =
  process.env.NEXT_PUBLIC_RPC_URL || "https://api.devnet.solana.com";

// ── Anchor program ID ───────────────────────────────────────
export const PROGRAM_ID = new PublicKey(
  process.env.NEXT_PUBLIC_PROGRAM_ID ||
    "F6dYHixw4PB4qCEERCYP19BxzKpuLV6JbbWRMUYrRZLY"
);

// ── USDC SPL Token mint (devnet) ────────────────────────────
export const USDC_MINT = new PublicKey(
  process.env.NEXT_PUBLIC_USDC_MINT ||
    "9yry7vqkhZGaynE37qX3FYpUqBx8z9n9MFNF8f1FP6Hm" // common devnet USDC mint
);

// ── Butler wallet (SPL token destination) ───────────────────
if (!process.env.NEXT_PUBLIC_BUTLER_ADDRESS) {
  throw new Error(
    "NEXT_PUBLIC_BUTLER_ADDRESS is required. Set it in your .env file."
  );
}
export const BUTLER_ADDRESS = new PublicKey(
  process.env.NEXT_PUBLIC_BUTLER_ADDRESS
);

// ── USDC decimals (standard for USDC on Solana) ────────────
export const USDC_DECIMALS = 6;

// ── Explorer base URL ──────────────────────────────────────
export const EXPLORER_URL = "https://explorer.solana.com";
export const CLUSTER = "devnet";

/** Build a Solana Explorer link for an address or transaction */
export function explorerLink(
  value: string,
  type: "address" | "tx" = "address"
): string {
  return `${EXPLORER_URL}/${type}/${value}?cluster=${CLUSTER}`;
}
