// Base Sepolia testnet chain config & contract ABIs for frontend use

export const BASE_SEPOLIA_CHAIN = {
  id: 84532,
  name: "Base Sepolia",
  rpcUrl: "https://sepolia.base.org",
  explorer: "https://sepolia.basescan.org",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
} as const;

export const CONTRACT_ADDRESSES = {
  AgentRegistry: (process.env.NEXT_PUBLIC_AGENT_REGISTRY || "") as `0x${string}`,
  OrderBook: (process.env.NEXT_PUBLIC_ORDERBOOK_ADDRESS || "") as `0x${string}`,
  Escrow: (process.env.NEXT_PUBLIC_ESCROW_ADDRESS || "") as `0x${string}`,
  USDC: (process.env.NEXT_PUBLIC_USDC_ADDRESS || "") as `0x${string}`,
} as const;

export function explorerAddress(addr: string) {
  return `${BASE_SEPOLIA_CHAIN.explorer}/address/${addr}`;
}

export function explorerTx(hash: string) {
  return `${BASE_SEPOLIA_CHAIN.explorer}/tx/${hash}`;
}

// Minimal ABIs — only the functions/events the frontend needs

export const AGENT_REGISTRY_ABI = [
  {
    type: "function",
    name: "getDeveloper",
    inputs: [{ name: "agent", type: "address" }],
    outputs: [{ name: "", type: "address" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "isAgentActive",
    inputs: [{ name: "wallet", type: "address" }],
    outputs: [{ name: "", type: "bool" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "getAgent",
    inputs: [{ name: "wallet", type: "address" }],
    outputs: [
      {
        name: "",
        type: "tuple",
        components: [
          { name: "developer", type: "address" },
          { name: "name", type: "string" },
          { name: "metadataURI", type: "string" },
          { name: "capabilities", type: "string[]" },
          { name: "reputation", type: "uint256" },
          { name: "status", type: "uint8" },
          { name: "createdAt", type: "uint256" },
          { name: "updatedAt", type: "uint256" },
        ],
      },
    ],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "agentCount",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "getAllAgents",
    inputs: [],
    outputs: [
      {
        name: "list",
        type: "tuple[]",
        components: [
          { name: "developer", type: "address" },
          { name: "name", type: "string" },
          { name: "metadataURI", type: "string" },
          { name: "capabilities", type: "string[]" },
          { name: "reputation", type: "uint256" },
          { name: "status", type: "uint8" },
          { name: "createdAt", type: "uint256" },
          { name: "updatedAt", type: "uint256" },
        ],
      },
    ],
    stateMutability: "view",
  },
  // Writes
  {
    type: "function",
    name: "registerAgent",
    inputs: [
      { name: "agentAddress", type: "address" },
      { name: "name", type: "string" },
      { name: "metadataURI", type: "string" },
      { name: "capabilities", type: "string[]" },
    ],
    outputs: [],
    stateMutability: "nonpayable",
  },
  // Events
  {
    type: "event",
    name: "AgentRegistered",
    inputs: [
      { name: "agentAddress", type: "address", indexed: true },
      { name: "developer", type: "address", indexed: true },
      { name: "name", type: "string", indexed: false },
      { name: "metadataURI", type: "string", indexed: false },
    ],
  },
] as const;
