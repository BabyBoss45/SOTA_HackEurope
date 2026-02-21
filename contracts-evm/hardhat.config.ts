// DEPRECATED — The project has migrated to Solana (see /anchor/).
// These EVM contracts on Base Sepolia are no longer in use.

import { config as dotenvConfig } from "dotenv";
import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import path from "path";

dotenvConfig({ path: path.resolve(__dirname, ".env") });
dotenvConfig({ path: path.resolve(__dirname, "..", ".env") });

const accounts = process.env.PRIVATE_KEY
  ? [process.env.PRIVATE_KEY]
  : [];

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  defaultNetwork: "hardhat",
  networks: {
    hardhat: {
      chainId: 31337,
    },

    // ─── Base Networks ──────────────────────────────────────
    baseSepolia: {
      url: process.env.BASE_RPC_URL || "https://sepolia.base.org",
      chainId: 84532,
      accounts,
    },
    baseMainnet: {
      url: "https://mainnet.base.org",
      chainId: 8453,
      accounts,
    },
  },
};

export default config;
