import { config as dotenvConfig } from "dotenv";
import { ethers } from "hardhat";
import path from "path";
import { promises as fs } from "fs";

dotenvConfig({ path: path.resolve(__dirname, "..", "..", ".env") });

async function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries = 5,
  baseDelay = 2000
): Promise<T> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error: any) {
      const isRetryable =
        error?.message?.includes("Too Many Requests") ||
        error?.code === "ECONNRESET" ||
        error?.code === "ETIMEDOUT";
      if (!isRetryable || i === maxRetries - 1) throw error;
      const delayMs = baseDelay * Math.pow(2, i);
      console.log(
        `Retrying in ${delayMs}ms... (attempt ${i + 1}/${maxRetries})`
      );
      await delay(delayMs);
    }
  }
  throw new Error("Max retries exceeded");
}

async function main() {
  const [deployer] = await ethers.getSigners();
  const network = await deployer.provider!.getNetwork();
  const chainId = Number(network.chainId);

  // ─── Network Naming ─────────────────────────────────────
  let networkName: string;
  let nativeCurrency: string;
  if (chainId === 84532) {
    networkName = "base-sepolia";
    nativeCurrency = "ETH";
  } else if (chainId === 8453) {
    networkName = "base-mainnet";
    nativeCurrency = "ETH";
  } else if (chainId === 31337) {
    networkName = "hardhat-local";
    nativeCurrency = "ETH";
  } else {
    networkName = `chain-${chainId}`;
    nativeCurrency = "ETH";
  }

  console.log(`\nDeploying SOTA contracts to ${networkName} (Chain ID: ${chainId})`);
  console.log(`   Deployer: ${deployer.address}`);
  const balance = await deployer.provider!.getBalance(deployer.address);
  console.log(`   Balance:  ${ethers.formatEther(balance)} ${nativeCurrency}\n`);

  // ═══════════════════════════════════════════════════════════
  // 1. USDC Token (MockUSDC for local/testnet, or use existing)
  // ═══════════════════════════════════════════════════════════

  let usdcAddress: string;

  if (chainId === 31337) {
    // Local: always deploy MockUSDC
    console.log("Deploying MockUSDC (local mode)...");
    const mockUsdc = await retryWithBackoff(() =>
      ethers.deployContract("MockUSDC")
    );
    await retryWithBackoff(() => mockUsdc.waitForDeployment());
    usdcAddress = mockUsdc.target as string;
    console.log(`   MockUSDC: ${usdcAddress}`);
  } else if (chainId === 84532) {
    // Base Sepolia: use env var or deploy MockUSDC
    usdcAddress = process.env.USDC_ADDRESS || "DEPLOY_MOCK";
    if (usdcAddress === "DEPLOY_MOCK") {
      console.log("Deploying MockUSDC (Base Sepolia — no official testnet USDC)...");
      const mockUsdc = await retryWithBackoff(() =>
        ethers.deployContract("MockUSDC")
      );
      await retryWithBackoff(() => mockUsdc.waitForDeployment());
      usdcAddress = mockUsdc.target as string;
      console.log(`   MockUSDC: ${usdcAddress}`);
    } else {
      console.log(`   Using USDC: ${usdcAddress}`);
    }
  } else {
    // Mainnet: must set USDC_ADDRESS
    usdcAddress = process.env.USDC_ADDRESS!;
    if (!usdcAddress) throw new Error("USDC_ADDRESS env var required for mainnet");
    console.log(`   Using USDC: ${usdcAddress}`);
  }
  await delay(2000);

  // ═══════════════════════════════════════════════════════════
  // 2. OrderBook
  // ═══════════════════════════════════════════════════════════

  console.log("Deploying OrderBook...");
  const orderBook = await retryWithBackoff(() =>
    ethers.deployContract("OrderBook", [deployer.address])
  );
  await retryWithBackoff(() => orderBook.waitForDeployment());
  const orderBookAddress = orderBook.target as string;
  console.log(`   OrderBook: ${orderBookAddress}`);
  await delay(2000);

  // ═══════════════════════════════════════════════════════════
  // 3. Escrow
  // ═══════════════════════════════════════════════════════════

  console.log("Deploying Escrow...");
  const escrow = await retryWithBackoff(() =>
    ethers.deployContract("Escrow", [
      deployer.address,
      usdcAddress,
      deployer.address, // fee collector = deployer for now
    ])
  );
  await retryWithBackoff(() => escrow.waitForDeployment());
  const escrowAddress = escrow.target as string;
  console.log(`   Escrow: ${escrowAddress}`);
  await delay(2000);

  // ═══════════════════════════════════════════════════════════
  // 4. AgentRegistry
  // ═══════════════════════════════════════════════════════════

  console.log("Deploying AgentRegistry...");
  const agentRegistry = await retryWithBackoff(() =>
    ethers.deployContract("AgentRegistry", [deployer.address])
  );
  await retryWithBackoff(() => agentRegistry.waitForDeployment());
  const agentRegistryAddress = agentRegistry.target as string;
  console.log(`   AgentRegistry: ${agentRegistryAddress}`);
  await delay(2000);

  // ═══════════════════════════════════════════════════════════
  // 5. Wire contracts together
  // ═══════════════════════════════════════════════════════════

  console.log("\nWiring contracts...");

  console.log("   OrderBook.setEscrow -> Escrow");
  await retryWithBackoff(() => (orderBook as any).setEscrow(escrowAddress));
  await delay(2000);

  console.log("   Escrow.setOrderBook -> OrderBook");
  await retryWithBackoff(() => (escrow as any).setOrderBook(orderBookAddress));
  await delay(2000);

  // ═══════════════════════════════════════════════════════════
  // 6. Save deployment artifacts
  // ═══════════════════════════════════════════════════════════

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const deploymentRecord = {
    network: networkName,
    chainId,
    deployedAt: new Date().toISOString(),
    deployer: deployer.address,
    contracts: {
      USDC: usdcAddress,
      OrderBook: orderBookAddress,
      Escrow: escrowAddress,
      AgentRegistry: agentRegistryAddress,
    },
  };

  const deploymentsDir = path.join(__dirname, "..", "deployments");
  await fs.mkdir(deploymentsDir, { recursive: true });

  const timestampedPath = path.join(
    deploymentsDir,
    `${networkName}-${chainId}-${timestamp}.json`
  );
  await fs.writeFile(timestampedPath, JSON.stringify(deploymentRecord, null, 2));

  const latestPath = path.join(
    deploymentsDir,
    `${networkName}-${chainId}.json`
  );
  await fs.writeFile(latestPath, JSON.stringify(deploymentRecord, null, 2));

  console.log("\nDeployment complete!");
  console.log("Saved to:");
  console.log(`   ${timestampedPath}`);
  console.log(`   ${latestPath}`);

  console.log("\nContract Addresses:");
  console.log(`   USDC:          ${usdcAddress}`);
  console.log(`   OrderBook:     ${orderBookAddress}`);
  console.log(`   Escrow:        ${escrowAddress}`);
  console.log(`   AgentRegistry: ${agentRegistryAddress}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
