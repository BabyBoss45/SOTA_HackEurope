import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import {
  Connection,
  Keypair,
  PublicKey,
  SystemProgram,
  SYSVAR_RENT_PUBKEY,
} from "@solana/web3.js";
import { mintTo, getAssociatedTokenAddress, TOKEN_PROGRAM_ID } from "@solana/spl-token";
import { AnchorProvider, Program, BN, Wallet } from "@coral-xyz/anchor";
import bs58 from "bs58";
import { prisma } from "@/src/lib/prisma";

// IDL type import from Anchor build output
import idl from "../../../../../anchor/target/idl/sota_marketplace.json";

export const runtime = "nodejs";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: "2026-01-28.clover",
});

// In-memory idempotency guard (hackathon scope -- use Redis/DB in production)
// Map<eventId, timestamp> with TTL to prevent unbounded growth in long-running servers
const IDEMPOTENCY_TTL_MS = 300_000; // 5 minutes
const IDEMPOTENCY_MAX_SIZE = 10_000;
const processedEventIds = new Map<string, number>();

/** Remove entries older than IDEMPOTENCY_TTL_MS to bound memory usage. */
function pruneProcessedEvents(): void {
  if (processedEventIds.size <= IDEMPOTENCY_MAX_SIZE) return;
  const now = Date.now();
  for (const [id, timestamp] of processedEventIds) {
    if (now - timestamp > IDEMPOTENCY_TTL_MS) {
      processedEventIds.delete(id);
    }
  }
}

const PROGRAM_ID = new PublicKey(
  process.env.NEXT_PUBLIC_PROGRAM_ID || "EuGy9m9G5H5QNm3YaHQ26Peo5ZTABqWHk83R3AT2nYSD"
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Load a Solana Keypair from either a base58 string or a JSON byte array. */
function loadKeypair(raw: string): Keypair {
  try {
    // Try JSON array first (e.g. "[1,2,3,...]")
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return Keypair.fromSecretKey(Uint8Array.from(parsed));
    }
  } catch {
    // Not JSON -- fall through to base58
  }
  return Keypair.fromSecretKey(bs58.decode(raw));
}

/** Derive a PDA given seeds and the program ID. */
function findPDA(seeds: (Buffer | Uint8Array)[]): PublicKey {
  const [pda] = PublicKey.findProgramAddressSync(seeds, PROGRAM_ID);
  return pda;
}

/** Convert a u64 number to a little-endian 8-byte Buffer for PDA derivation. */
function u64ToLeBytes(value: number | bigint): Buffer {
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64LE(BigInt(value));
  return buf;
}

// ---------------------------------------------------------------------------
// Webhook handler
// ---------------------------------------------------------------------------

export async function POST(request: NextRequest) {
  const body = await request.text();
  const sig = request.headers.get("stripe-signature");

  if (!sig) {
    return NextResponse.json({ error: "Missing stripe-signature" }, { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      body,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err: any) {
    console.error("Webhook signature verification failed:", err.message);
    return NextResponse.json({ error: "Invalid signature" }, { status: 400 });
  }

  // Idempotency: skip already-processed events (Stripe retries on timeout)
  const existingTimestamp = processedEventIds.get(event.id);
  if (existingTimestamp !== undefined && Date.now() - existingTimestamp < IDEMPOTENCY_TTL_MS) {
    console.log(`Skipping duplicate event ${event.id}`);
    return NextResponse.json({ received: true });
  }
  processedEventIds.set(event.id, Date.now());
  pruneProcessedEvents();

  if (event.type === "payment_intent.succeeded") {
    const paymentIntent = event.data.object as Stripe.PaymentIntent;
    const { jobId, agentAddress, usdcAmountRaw, boardJobId } = paymentIntent.metadata;

    console.log(`Payment succeeded for job ${jobId}, amount: ${usdcAmountRaw} (raw USDC)`);

    try {
      // Validate required env vars before on-chain operations
      const platformKeyRaw = process.env.PLATFORM_PRIVATE_KEY;
      const usdcMintStr = process.env.NEXT_PUBLIC_USDC_MINT;
      if (!platformKeyRaw || !usdcMintStr) {
        throw new Error("Missing PLATFORM_PRIVATE_KEY or NEXT_PUBLIC_USDC_MINT");
      }

      // --- Solana setup ---
      const platformKeypair = loadKeypair(platformKeyRaw);
      const connection = new Connection(
        process.env.RPC_URL || process.env.NEXT_PUBLIC_RPC_URL || "https://api.devnet.solana.com",
        "confirmed"
      );
      const wallet = new Wallet(platformKeypair);
      const provider = new AnchorProvider(connection, wallet, {
        commitment: "confirmed",
      });
      const program = new Program(idl as any, provider);

      const usdcMint = new PublicKey(usdcMintStr);
      const providerPubkey = new PublicKey(agentAddress);
      const amount = BigInt(usdcAmountRaw);
      const onChainJobId = boardJobId ? parseInt(boardJobId, 10) : null;

      if (onChainJobId == null) {
        throw new Error("boardJobId (on-chain job ID) is required for escrow funding");
      }

      // Derive the platform's associated token account for USDC
      const platformATA = await getAssociatedTokenAddress(
        usdcMint,
        platformKeypair.publicKey
      );

      // Step 1: Mint mock USDC to platform wallet (devnet faucet mint)
      // The platform keypair must be the mint authority on devnet.
      console.log(`Minting ${usdcAmountRaw} USDC to ${platformKeypair.publicKey.toBase58()}...`);
      const mintTxSig = await mintTo(
        connection,
        platformKeypair, // payer
        usdcMint,        // mint
        platformATA,     // destination ATA
        platformKeypair, // mint authority
        amount
      );
      console.log(`Mint confirmed: ${mintTxSig}`);

      // Step 2: Fund the escrow via Anchor program
      // Derive PDAs
      const jobIdBytes = u64ToLeBytes(onChainJobId);
      const configPDA = findPDA([Buffer.from("config")]);
      const jobPDA = findPDA([Buffer.from("job"), jobIdBytes]);
      const depositPDA = findPDA([Buffer.from("deposit"), jobIdBytes]);
      const escrowVaultPDA = findPDA([Buffer.from("escrow_vault"), jobIdBytes]);

      console.log(`Funding escrow for on-chain job ${onChainJobId}, provider ${agentAddress}...`);
      const fundTxSig = await program.methods
        .fundJob(new BN(amount.toString()))
        .accounts({
          config: configPDA,
          job: jobPDA,
          deposit: depositPDA,
          escrowVault: escrowVaultPDA,
          posterAta: platformATA,
          usdcMint: usdcMint,
          poster: platformKeypair.publicKey,
          provider: providerPubkey,
          tokenProgram: TOKEN_PROGRAM_ID,
          systemProgram: SystemProgram.programId,
          rent: SYSVAR_RENT_PUBKEY,
        })
        .rpc();
      console.log(`Escrow funded: ${fundTxSig}`);

      console.log(`All on-chain operations complete for job ${jobId}`);

      // Persist Payment record (funded)
      try {
        await prisma.payment.create({
          data: {
            jobId: jobId,
            onChainJobId: onChainJobId,
            paymentIntentId: paymentIntent.id,
            amountCents: paymentIntent.amount,
            usdcAmountRaw: usdcAmountRaw,
            agentAddress: agentAddress,
            status: "funded",
          },
        });
        console.log(`Payment record created (funded) for job ${jobId}`);
      } catch (dbErr: any) {
        console.error("Failed to create Payment record:", dbErr);
      }
    } catch (chainErr: any) {
      console.error("On-chain operations failed:", chainErr);
      // Payment succeeded but chain ops failed -- log for manual resolution
      // Still create a Payment record so we can track the Stripe charge
      try {
        await prisma.payment.create({
          data: {
            jobId: jobId,
            paymentIntentId: paymentIntent.id,
            amountCents: paymentIntent.amount,
            usdcAmountRaw: usdcAmountRaw,
            agentAddress: agentAddress,
            status: "pending",
          },
        });
        console.log(`Payment record created (pending -- chain ops failed) for job ${jobId}`);
      } catch (dbErr: any) {
        console.error("Failed to create Payment record:", dbErr);
      }
    }
  }

  return NextResponse.json({ received: true });
}
