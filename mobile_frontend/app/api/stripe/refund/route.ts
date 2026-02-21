import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { ethers } from "ethers";
import { prisma } from "@/src/lib/prisma";

export const runtime = "nodejs";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: "2026-01-28.clover",
});

const ESCROW_ABI = [
  "function refund(uint256 jobId) external",
  "function getDeposit(uint256 jobId) external view returns (address poster, address provider, uint256 amount, bool funded, bool released, bool refunded)",
];

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

  // Atomic compare-and-swap: only proceed if status is still funded or pending
  const updated = await prisma.payment.updateMany({
    where: { jobId: job_id, status: { in: ["funded", "pending"] } },
    data: { status: "refund_requested", refundReason: reason || null },
  });
  if (updated.count === 0) {
    return NextResponse.json(
      { error: "Refund already in progress or completed", job_id },
      { status: 409 }
    );
  }

  let escrowRefundTxHash: string | null = null;
  let stripeRefundId: string | null = null;

  // Step 1: On-chain refund (skip if escrow was never funded)
  if (payment.status === "funded" && payment.onChainJobId != null) {
    try {
      const platformKey = process.env.PLATFORM_PRIVATE_KEY;
      const escrowAddress = process.env.NEXT_PUBLIC_ESCROW_ADDRESS;
      if (!platformKey || !escrowAddress) {
        throw new Error("Missing PLATFORM_PRIVATE_KEY or NEXT_PUBLIC_ESCROW_ADDRESS");
      }

      const provider = new ethers.JsonRpcProvider(
        process.env.RPC_URL || "https://sepolia.base.org"
      );
      const signer = new ethers.Wallet(platformKey, provider);
      const escrow = new ethers.Contract(escrowAddress, ESCROW_ABI, signer);

      // Check deposit state before attempting refund
      const deposit = await escrow.getDeposit(payment.onChainJobId);
      const [, , , funded, released, refunded] = deposit;

      if (refunded) {
        console.log(`Escrow already refunded for on-chain job ${payment.onChainJobId}`);
      } else if (!funded || released) {
        console.log(`Escrow not in refundable state for on-chain job ${payment.onChainJobId} (funded=${funded}, released=${released})`);
      } else {
        const refundTx = await escrow.refund(payment.onChainJobId);
        const receipt = await refundTx.wait();
        escrowRefundTxHash = receipt.hash;
        console.log(`Escrow refunded for on-chain job ${payment.onChainJobId}: ${escrowRefundTxHash}`);
      }
    } catch (chainErr: any) {
      console.error("On-chain refund failed:", chainErr);
      // Continue with Stripe refund — customer getting card money back is the priority
    }
  }

  // Step 2: Stripe refund
  try {
    const refund = await stripe.refunds.create({
      payment_intent: payment.paymentIntentId,
      amount: payment.amountCents,
    });
    stripeRefundId = refund.id;
    console.log(`Stripe refund issued: ${stripeRefundId} for payment_intent ${payment.paymentIntentId}`);
  } catch (stripeErr: any) {
    // Handle already-refunded charge gracefully
    if (stripeErr.code === "charge_already_refunded") {
      console.log(`Stripe charge already refunded for ${payment.paymentIntentId}`);
      stripeRefundId = "already_refunded";
    } else {
      console.error("Stripe refund failed:", stripeErr);
      // Mark as failed — on-chain may have succeeded but Stripe didn't
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
