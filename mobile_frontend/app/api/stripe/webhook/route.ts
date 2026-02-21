import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { ethers } from "ethers";

export const runtime = "nodejs";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: "2026-01-28.clover",
});

// In-memory idempotency guard (hackathon scope — use Redis/DB in production)
const processedEventIds = new Set<string>();

const MOCK_USDC_ABI = [
  "function mint(address to, uint256 amount) external",
  "function approve(address spender, uint256 amount) external returns (bool)",
];

const ESCROW_ABI = [
  "function fundJob(uint256 jobId, address provider, uint256 amount) external",
];

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
  if (processedEventIds.has(event.id)) {
    console.log(`Skipping duplicate event ${event.id}`);
    return NextResponse.json({ received: true });
  }
  processedEventIds.add(event.id);

  if (event.type === "payment_intent.succeeded") {
    const paymentIntent = event.data.object as Stripe.PaymentIntent;
    const { jobId, agentAddress, usdcAmountRaw, boardJobId } = paymentIntent.metadata;

    console.log(`Payment succeeded for job ${jobId}, amount: ${usdcAmountRaw} (raw USDC)`);

    try {
      // Validate required env vars before on-chain operations
      const platformKey = process.env.PLATFORM_PRIVATE_KEY;
      const usdcAddress = process.env.NEXT_PUBLIC_USDC_ADDRESS;
      const escrowAddress = process.env.NEXT_PUBLIC_ESCROW_ADDRESS;
      if (!platformKey || !usdcAddress || !escrowAddress) {
        throw new Error("Missing PLATFORM_PRIVATE_KEY, NEXT_PUBLIC_USDC_ADDRESS, or NEXT_PUBLIC_ESCROW_ADDRESS");
      }

      // Connect to Base Sepolia
      const provider = new ethers.JsonRpcProvider(
        process.env.RPC_URL || "https://sepolia.base.org"
      );
      const signer = new ethers.Wallet(platformKey, provider);

      const mockUsdc = new ethers.Contract(usdcAddress, MOCK_USDC_ABI, signer);
      const escrow = new ethers.Contract(escrowAddress, ESCROW_ABI, signer);

      const amount = BigInt(usdcAmountRaw);

      // Step 1: Mint MockUSDC to platform wallet
      console.log(`Minting ${usdcAmountRaw} MockUSDC to ${signer.address}...`);
      const mintTx = await mockUsdc.mint(signer.address, amount);
      await mintTx.wait();
      console.log(`Mint confirmed: ${mintTx.hash}`);

      // Step 2: Approve escrow to spend MockUSDC
      console.log(`Approving escrow ${escrowAddress} to spend ${usdcAmountRaw}...`);
      const approveTx = await mockUsdc.approve(escrowAddress, amount);
      await approveTx.wait();
      console.log(`Approve confirmed: ${approveTx.hash}`);

      // Step 3: Fund escrow
      console.log(`Funding escrow for job ${jobId}, agent ${agentAddress}...`);
      const fundTx = await escrow.fundJob(
        BigInt(jobId),
        agentAddress,
        amount
      );
      await fundTx.wait();
      console.log(`Escrow funded: ${fundTx.hash}`);

      console.log(`All on-chain operations complete for job ${jobId}`);
    } catch (chainErr: any) {
      console.error("On-chain operations failed:", chainErr);
      // Payment succeeded but chain ops failed — log for manual resolution
      // Don't return error to Stripe (payment is still valid)
    }
  }

  return NextResponse.json({ received: true });
}
