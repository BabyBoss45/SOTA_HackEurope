import { Connection, Keypair, PublicKey, clusterApiUrl } from "@solana/web3.js";
import {
  getOrCreateAssociatedTokenAccount,
  mintTo,
} from "@solana/spl-token";
import * as fs from "fs";

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.log("Usage: ts-node mint_usdc.ts <USDC_MINT> <RECIPIENT> [AMOUNT]");
    console.log("  AMOUNT defaults to 10,000 USDC");
    process.exit(1);
  }

  const usdcMint = new PublicKey(args[0]);
  const recipient = new PublicKey(args[1]);
  const amount = (args[2] ? parseFloat(args[2]) : 10_000) * 1_000_000; // USDC has 6 decimals

  const connection = new Connection(
    process.env.RPC_URL || clusterApiUrl("devnet"),
    "confirmed"
  );

  // Load mint authority keypair
  const keypairPath =
    process.env.KEYPAIR_PATH ||
    `${process.env.HOME}/.config/solana/id.json`;
  const secret = JSON.parse(fs.readFileSync(keypairPath, "utf-8"));
  const mintAuthority = Keypair.fromSecretKey(Uint8Array.from(secret));

  console.log("Mint authority:", mintAuthority.publicKey.toBase58());
  console.log("USDC Mint:", usdcMint.toBase58());
  console.log("Recipient:", recipient.toBase58());
  console.log("Amount:", amount / 1_000_000, "USDC");

  // Get or create ATA for recipient
  const ata = await getOrCreateAssociatedTokenAccount(
    connection,
    mintAuthority,
    usdcMint,
    recipient
  );
  console.log("Recipient ATA:", ata.address.toBase58());

  // Mint tokens
  const sig = await mintTo(
    connection,
    mintAuthority,
    usdcMint,
    ata.address,
    mintAuthority.publicKey,
    amount
  );

  console.log("Minted! Tx:", sig);
  console.log(
    `View on explorer: https://explorer.solana.com/tx/${sig}?cluster=devnet`
  );
}

main().catch(console.error);
