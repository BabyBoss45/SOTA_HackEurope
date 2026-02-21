import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import {
  Connection,
  Keypair,
  PublicKey,
} from "@solana/web3.js";
import { getAssociatedTokenAddress, TOKEN_PROGRAM_ID } from "@solana/spl-token";
import { AnchorProvider, Program, Wallet } from "@coral-xyz/anchor";
import bs58 from "bs58";
import { prisma } from "@/src/lib/prisma";

// IDL import from Anchor build output
import idl from "../../../../../anchor/target/idl/sota_marketplace.json";

export const runtime = "nodejs";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: "2026-01-28.clover",
});

const PROGRAM_ID = new PublicKey(
  process.env.NEXT_PUBLIC_PROGRAM_ID || "F6dYHixw4PB4qCEERCYP19BxzKpuLV6JbbWRMUYrRZLY"
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Load a Solana Keypair from either a base58 string or a JSON byte array. */
function loadKeypair(raw: string): Keypair {
  try {
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
// Refund handler
// ---------------------------------------------------------------------------

export async function POST(request: NextRequest) {
  // Authenticate via shared secret
  const apiKey = request.headers.get("x-internal-api-key");
  if (!apiKey || apiKey !== process.env.INTERNAL_API_KEY) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: { job_id: string; reason?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { job_id, reason } = body;
  if (!job_id) {
    return NextResponse.json({ error: "job_id is required" }, { status: 400 });
  }

  // Look up Payment by jobId
  const payment = await prisma.payment.findUnique({ where: { jobId: job_id } });
  if (!payment) {
    return NextResponse.json(
      { error: "No payment record found for this job", job_id },
      { status: 404 }
    );
  }

  // Idempotent: already refunded
  if (payment.status === "refunded") {
    return NextResponse.json({
      success: true,
      job_id,
      status: "refunded",
      message: "Already refunded",
      stripeRefundId: payment.stripeRefundId,
      escrowRefundTxHash: payment.escrowRefundTxHash,
    });
  }

  // Already in progress
  if (payment.status === "refund_requested") {
    return NextResponse.json(
      { error: "Refund already in progress", job_id },
      { status: 409 }
    );
  }

  // Atomic compare-and-swap: only proceed if status is still funded or pending.
  // Use an interactive transaction to ensure the CAS update and re-fetch happen
  // atomically, eliminating a race window between updateMany and findUnique.
  const previousStatus = payment.status;
  const casResult = await prisma.$transaction(async (tx) => {
    const updated = await tx.payment.updateMany({
      where: { jobId: job_id, status: { in: ["funded", "pending"] } },
      data: { status: "refund_requested", refundReason: reason || null },
    });
    if (updated.count === 0) {
      return null;
    }
    // Re-fetch within the same transaction to guarantee we read the row we just wrote
    return tx.payment.findUnique({ where: { jobId: job_id } });
  });

  if (!casResult) {
    return NextResponse.json(
      { error: "Refund already in progress or completed", job_id },
      { status: 409 }
    );
  }

  const updatedPayment = casResult;

  let escrowRefundTxHash: string | null = null;
  let stripeRefundId: string | null = null;

  // Step 1: On-chain refund (skip if escrow was never funded)
  // Use previousStatus to check the pre-CAS state, and updatedPayment for all other fields
  if (previousStatus === "funded" && updatedPayment.onChainJobId != null) {
    try {
      const platformKeyRaw = process.env.PLATFORM_PRIVATE_KEY;
      const usdcMintStr = process.env.NEXT_PUBLIC_USDC_MINT;
      if (!platformKeyRaw || !usdcMintStr) {
        throw new Error("Missing PLATFORM_PRIVATE_KEY or NEXT_PUBLIC_USDC_MINT");
      }

      const platformKeypair = loadKeypair(platformKeyRaw);
      const connection = new Connection(
        process.env.RPC_URL || process.env.NEXT_PUBLIC_RPC_URL || "https://api.devnet.solana.com",
        "confirmed"
      );
      const wallet = new Wallet(platformKeypair);
      const anchorProvider = new AnchorProvider(connection, wallet, {
        commitment: "confirmed",
      });
      const program = new Program(idl as any, anchorProvider);
      const usdcMint = new PublicKey(usdcMintStr);

      const onChainJobId = updatedPayment.onChainJobId!;
      const jobIdBytes = u64ToLeBytes(onChainJobId);

      // Derive PDAs
      const configPDA = findPDA([Buffer.from("config")]);
      const jobPDA = findPDA([Buffer.from("job"), jobIdBytes]);
      const depositPDA = findPDA([Buffer.from("deposit"), jobIdBytes]);
      const escrowVaultPDA = findPDA([Buffer.from("escrow_vault"), jobIdBytes]);

      // Fetch the deposit account to check current state
      // Cast through `any` because the generic Idl type doesn't expose named accounts
      const depositAccount = await (program.account as any).deposit.fetch(depositPDA) as {
        jobId: { toNumber(): number };
        poster: PublicKey;
        provider: PublicKey;
        amount: { toNumber(): number };
        funded: boolean;
        released: boolean;
        refunded: boolean;
        deliveryConfirmed: boolean;
        deliveryConfirmedAt: { toNumber(): number };
        bump: number;
      };

      if (depositAccount.refunded) {
        console.log(`Escrow already refunded for on-chain job ${onChainJobId}`);
      } else if (!depositAccount.funded || depositAccount.released) {
        console.log(
          `Escrow not in refundable state for on-chain job ${onChainJobId} ` +
          `(funded=${depositAccount.funded}, released=${depositAccount.released})`
        );
      } else {
        // Derive remaining accounts needed for the refund instruction
        const posterPubkey = depositAccount.poster as PublicKey;
        const providerPubkey = depositAccount.provider as PublicKey;

        const posterATA = await getAssociatedTokenAddress(usdcMint, posterPubkey);
        const reputationPDA = findPDA([
          Buffer.from("reputation"),
          providerPubkey.toBuffer(),
        ]);

        const refundTxSig = await program.methods
          .refund()
          .accounts({
            config: configPDA,
            job: jobPDA,
            deposit: depositPDA,
            escrowVault: escrowVaultPDA,
            posterAta: posterATA,
            reputation: reputationPDA,
            authority: platformKeypair.publicKey,
            tokenProgram: TOKEN_PROGRAM_ID,
          })
          .rpc();

        escrowRefundTxHash = refundTxSig;
        console.log(`Escrow refunded for on-chain job ${onChainJobId}: ${escrowRefundTxHash}`);
      }
    } catch (chainErr: any) {
      console.error("On-chain refund failed:", chainErr);
      // Continue with Stripe refund -- customer getting card money back is the priority
    }
  }

  // Step 2: Stripe refund
  try {
    const refund = await stripe.refunds.create({
      payment_intent: updatedPayment.paymentIntentId,
      amount: updatedPayment.amountCents,
    });
    stripeRefundId = refund.id;
    console.log(`Stripe refund issued: ${stripeRefundId} for payment_intent ${updatedPayment.paymentIntentId}`);
  } catch (stripeErr: any) {
    // Handle already-refunded charge gracefully
    if (stripeErr.code === "charge_already_refunded") {
      console.log(`Stripe charge already refunded for ${updatedPayment.paymentIntentId}`);
      stripeRefundId = "already_refunded";
    } else {
      console.error("Stripe refund failed:", stripeErr);
      // Mark as failed -- on-chain may have succeeded but Stripe didn't
      await prisma.payment.update({
        where: { jobId: job_id },
        data: {
          status: "refund_failed",
          escrowRefundTxHash,
          refundReason: reason || null,
        },
      });
      return NextResponse.json(
        {
          error: "Stripe refund failed",
          detail: stripeErr.message,
          escrowRefundTxHash,
          job_id,
        },
        { status: 500 }
      );
    }
  }

  // Step 3: Update Payment record
  await prisma.payment.update({
    where: { jobId: job_id },
    data: {
      status: "refunded",
      stripeRefundId,
      escrowRefundTxHash,
      refundReason: reason || null,
      refundedAt: new Date(),
    },
  });

  return NextResponse.json({
    success: true,
    job_id,
    status: "refunded",
    stripeRefundId,
    escrowRefundTxHash,
    message: "Refund completed",
  });
}
