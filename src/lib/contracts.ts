// Solana Devnet config & PDA derivation helpers for frontend use

import { PublicKey } from "@solana/web3.js";
import BN from "bn.js";

/* ── Program & Mint ── */

export const PROGRAM_ID = new PublicKey(
  process.env.NEXT_PUBLIC_PROGRAM_ID || "EuGy9m9G5H5QNm3YaHQ26Peo5ZTABqWHk83R3AT2nYSD"
);

export const USDC_MINT = new PublicKey(
  process.env.NEXT_PUBLIC_USDC_MINT || "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
);

/* ── Solana Cluster ── */

export const SOLANA_CLUSTER: "devnet" | "mainnet-beta" =
  (process.env.NEXT_PUBLIC_SOLANA_CLUSTER as "devnet" | "mainnet-beta") || "devnet";

export const SOLANA_RPC_URL =
  process.env.NEXT_PUBLIC_SOLANA_RPC_URL || "https://api.devnet.solana.com";

/* ── Explorer URL helpers ── */

export function getExplorerUrl(type: "tx" | "address", value: string): string {
  const cluster = SOLANA_CLUSTER === "mainnet-beta" ? "" : `?cluster=${SOLANA_CLUSTER}`;
  return `https://explorer.solana.com/${type}/${value}${cluster}`;
}

/** @deprecated Use getExplorerUrl("address", addr) instead */
export function explorerAddress(addr: string): string {
  return getExplorerUrl("address", addr);
}

/** @deprecated Use getExplorerUrl("tx", sig) instead */
export function explorerTx(sig: string): string {
  return getExplorerUrl("tx", sig);
}

/* ── Helpers ── */

/** Convert a u64 number to an 8-byte little-endian Buffer for PDA seeds. */
function u64ToLeBytes(id: number): Buffer {
  return new BN(id).toArrayLike(Buffer, "le", 8);
}

/** Shorthand: derive PDA and return only the PublicKey (discards bump). */
function findPda(seeds: (Buffer | Uint8Array)[]): PublicKey {
  const [pda] = PublicKey.findProgramAddressSync(seeds, PROGRAM_ID);
  return pda;
}

/* ── PDA derivation ── */

/** Global marketplace config PDA: seeds = [b"config"] */
export function getConfigPda(): PublicKey {
  return findPda([Buffer.from("config")]);
}

/** Job PDA: seeds = [b"job", job_id.to_le_bytes()] */
export function getJobPda(jobId: number): PublicKey {
  return findPda([Buffer.from("job"), u64ToLeBytes(jobId)]);
}

/** Bid PDA: seeds = [b"bid", bid_id.to_le_bytes()] */
export function getBidPda(bidId: number): PublicKey {
  return findPda([Buffer.from("bid"), u64ToLeBytes(bidId)]);
}

/** Deposit (escrow record) PDA: seeds = [b"deposit", job_id.to_le_bytes()] */
export function getDepositPda(jobId: number): PublicKey {
  return findPda([Buffer.from("deposit"), u64ToLeBytes(jobId)]);
}

/** Escrow vault (token account) PDA: seeds = [b"escrow_vault", job_id.to_le_bytes()] */
export function getEscrowVaultPda(jobId: number): PublicKey {
  return findPda([Buffer.from("escrow_vault"), u64ToLeBytes(jobId)]);
}

/** Agent profile PDA: seeds = [b"agent", wallet.as_ref()] */
export function getAgentPda(wallet: PublicKey): PublicKey {
  return findPda([Buffer.from("agent"), wallet.toBuffer()]);
}

/** Reputation PDA: seeds = [b"reputation", wallet.as_ref()] */
export function getReputationPda(wallet: PublicKey): PublicKey {
  return findPda([Buffer.from("reputation"), wallet.toBuffer()]);
}

/* ── Address formatting ── */

/** Shorten a base58 address for display: "7xKXt...3fGh" */
export function shortAddr(addr: string): string {
  if (addr.length <= 10) return addr;
  return `${addr.slice(0, 5)}...${addr.slice(-4)}`;
}

/** Validate a base58 Solana address. Returns true if valid. */
export function isValidSolanaAddress(addr: string): boolean {
  try {
    new PublicKey(addr);
    return true;
  } catch {
    return false;
  }
}
