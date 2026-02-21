import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: "2026-01-28.clover",
});

export async function POST(request: NextRequest) {
  try {
    const { jobId, amount, agentAddress, boardJobId } = await request.json();

    if (!jobId || !agentAddress) {
      return NextResponse.json(
        { error: "Missing required fields: jobId, agentAddress" },
        { status: 400 }
      );
    }

    if (typeof amount !== "number" || amount <= 0 || amount > 10000) {
      return NextResponse.json(
        { error: "amount must be a number between 0 and 10,000" },
        { status: 400 }
      );
    }

    // Convert USDC amount to USD cents (1 USDC ~ $1)
    const amountCents = Math.max(Math.round(amount * 100), 50); // Stripe minimum $0.50

    const paymentIntent = await stripe.paymentIntents.create({
      amount: amountCents,
      currency: "usd",
      automatic_payment_methods: { enabled: true },
      metadata: {
        jobId: String(jobId),
        agentAddress,
        usdcAmountRaw: String(Math.round(amount * 1e6)), // 6 decimals for USDC
        boardJobId: boardJobId || "",
      },
    });

    return NextResponse.json({ clientSecret: paymentIntent.client_secret });
  } catch (err: any) {
    console.error("PaymentIntent creation failed:", err);
    return NextResponse.json(
      { error: err.message || "Failed to create payment intent" },
      { status: 500 }
    );
  }
}
