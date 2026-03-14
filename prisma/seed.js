/* eslint-disable @typescript-eslint/no-require-imports */
// Simple seed script to create a demo user and sample agents
require("dotenv").config();
const { PrismaClient } = require("@prisma/client");
const bcrypt = require("bcryptjs");

const prisma = new PrismaClient();

async function main() {
  const existing = await prisma.user.findUnique({
    where: { email: "demo@sota.ai" },
  });

  const passwordHash = await bcrypt.hash("password123", 10);

  const user =
    existing ??
    (await prisma.user.create({
      data: {
        email: "demo@sota.ai",
        name: "Demo User",
        passwordHash,
        walletAddress: "11111111111111111111111111111111",
      },
    }));

  await prisma.agent.upsert({
    where: { id: 1 },
    update: {},
    create: {
      title: "Lead Gen Agent",
      description:
        "Automates outreach and captures qualified leads across email and LinkedIn.",
      category: "Sales",
      priceUsd: 49,
      tags: "leadgen,outreach,crm",
      network: "solana-devnet",
      ownerId: user.id,
    },
  });

  await prisma.agent.upsert({
    where: { id: 2 },
    update: {},
    create: {
      title: "Support Copilot",
      description:
        "Triage and respond to support tickets with human-in-the-loop approvals.",
      category: "Support",
      priceUsd: 29,
      tags: "support,helpdesk",
      network: "solana-devnet",
      ownerId: user.id,
    },
  });

  await prisma.agent.upsert({
    where: { id: 3 },
    update: {},
    create: {
      title: "Fun Activity",
      description:
        "Find something fun with zero friction. Uses your location, calendar, budget, and past events to recommend concerts, workshops, exhibitions, comedy, and more. Learns your preferences over time.",
      category: "Events",
      priceUsd: 3,
      tags: "events,fun,recommendations",
      network: "solana-devnet",
      ownerId: user.id,
      icon: "PartyPopper",
    },
  });

  await prisma.agent.upsert({
    where: { id: 4 },
    update: {},
    create: {
      title: "Nightlife & Adventure",
      description:
        "GPT-4o powered nightlife scout. Finds clubs, rooftop bars, underground parties, secret cinema, escape rooms, and late-night food tours. Competes with Claude's Fun Activity Agent — edgier, bolder, more spontaneous.",
      category: "Events",
      priceUsd: 3,
      tags: "nightlife,adventure,clubs,events",
      network: "solana-devnet",
      ownerId: user.id,
      icon: "Zap",
    },
  });

  // Seed MarketplaceJob records for demo
  await prisma.marketplaceJob.createMany({
    data: [
      {
        jobId: "seed-001",
        description: "Register team for ETHGlobal hackathon in Brussels",
        tags: ["hackathon_registration"],
        budgetUsdc: 5.0,
        status: "open",
        poster: "11111111111111111111111111111111",
      },
      {
        jobId: "seed-002",
        description: "Scrape competitor pricing from 3 e-commerce sites",
        tags: ["web-scrape", "data"],
        budgetUsdc: 8.0,
        status: "open",
        poster: "11111111111111111111111111111111",
      },
      {
        jobId: "seed-003",
        description: "Book a restaurant for 4 in Stockholm city center, Italian cuisine",
        tags: ["booking", "restaurant"],
        budgetUsdc: 3.0,
        status: "assigned",
        poster: "11111111111111111111111111111111",
        winner: "BookingAgent",
        winnerPrice: 2.80,
      },
      {
        jobId: "seed-004",
        description: "Summarize Q4 2025 earnings report for Tesla",
        tags: ["analysis", "document"],
        budgetUsdc: 12.0,
        status: "completed",
        poster: "11111111111111111111111111111111",
        winner: "AnalystPro",
        winnerPrice: 5.50,
      },
    ],
    skipDuplicates: true,
  });
}

main()
  .then(async () => {
    await prisma.$disconnect();
  })
  .catch(async (e) => {
    console.error(e);
    await prisma.$disconnect();
    process.exit(1);
  });

