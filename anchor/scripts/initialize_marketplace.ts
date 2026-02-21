import { Connection, Keypair, PublicKey, clusterApiUrl } from "@solana/web3.js";
import { Program, AnchorProvider, Wallet } from "@coral-xyz/anchor";
import * as fs from "fs";

const PROGRAM_ID = "F6dYHixw4PB4qCEERCYP19BxzKpuLV6JbbWRMUYrRZLY";
const USDC_MINT = process.argv[2] || "9yry7vqkhZGaynE37qX3FYpUqBx8z9n9MFNF8f1FP6Hm";

async function main() {
  const connection = new Connection(
    process.env.RPC_URL || clusterApiUrl("devnet"),
    "confirmed"
  );

  const keypairPath =
    process.env.KEYPAIR_PATH ||
    `${process.env.HOME}/.config/solana/id.json`;
  const secret = JSON.parse(fs.readFileSync(keypairPath, "utf-8"));
  const deployer = Keypair.fromSecretKey(Uint8Array.from(secret));

  console.log("Deployer:", deployer.publicKey.toBase58());
  console.log("Program ID:", PROGRAM_ID);
  console.log("USDC Mint:", USDC_MINT);

  const wallet = new Wallet(deployer);
  const provider = new AnchorProvider(connection, wallet, {
    commitment: "confirmed",
  });

  const idl = JSON.parse(
    fs.readFileSync("./target/idl/sota_marketplace.json", "utf-8")
  );
  const program = new Program(idl as any, provider);

  const [configPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("config")],
    new PublicKey(PROGRAM_ID)
  );
  console.log("Config PDA:", configPda.toBase58());

  // Check if config already exists
  const existing = await connection.getAccountInfo(configPda);
  if (existing) {
    console.log("Config PDA already exists! Marketplace already initialized.");
    return;
  }

  const tx = await program.methods
    .initialize(200) // 2% platform fee
    .accounts({
      config: configPda,
      authority: deployer.publicKey,
      usdcMint: new PublicKey(USDC_MINT),
      feeCollector: deployer.publicKey,
      systemProgram: new PublicKey("11111111111111111111111111111111"),
    } as any)
    .signers([deployer])
    .rpc();

  console.log("\nMarketplace initialized!");
  console.log("Transaction:", tx);
  console.log("Config PDA:", configPda.toBase58());
  console.log("Platform fee: 200 bps (2%)");
  console.log("Authority:", deployer.publicKey.toBase58());
  console.log("Fee collector:", deployer.publicKey.toBase58());
}

main().catch(console.error);
