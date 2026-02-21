import { Connection, Keypair, clusterApiUrl } from "@solana/web3.js";
import { createMint } from "@solana/spl-token";
import * as fs from "fs";

async function main() {
  const connection = new Connection(
    process.env.RPC_URL || clusterApiUrl("devnet"),
    "confirmed"
  );

  // Load deployer keypair
  const keypairPath =
    process.env.KEYPAIR_PATH ||
    `${process.env.HOME}/.config/solana/id.json`;
  const secret = JSON.parse(fs.readFileSync(keypairPath, "utf-8"));
  const deployer = Keypair.fromSecretKey(Uint8Array.from(secret));

  console.log("Deployer:", deployer.publicKey.toBase58());
  console.log(
    "Balance:",
    (await connection.getBalance(deployer.publicKey)) / 1e9,
    "SOL"
  );

  // Create USDC mock mint with 6 decimals
  const mint = await createMint(
    connection,
    deployer,
    deployer.publicKey, // mint authority
    deployer.publicKey, // freeze authority
    6 // decimals
  );

  console.log("USDC Mint created:", mint.toBase58());
  console.log("\nAdd to .env files:");
  console.log(`NEXT_PUBLIC_USDC_MINT=${mint.toBase58()}`);
  console.log(`USDC_MINT=${mint.toBase58()}`);
}

main().catch(console.error);
