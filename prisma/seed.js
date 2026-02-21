/* eslint-disable @typescript-eslint/no-require-imports */
require("dotenv").config();
const { PrismaClient } = require("@prisma/client");
const bcrypt = require("bcryptjs");

const prisma = new PrismaClient();

const agents = [
  {
    title: "Butler",
    description:
      "Your AI concierge orchestrating all agents — answers questions, collects intent, posts jobs, monitors bids, and delivers results.",
    category: "Orchestration",
    icon: "Bot",
    priceUsd: 0,
  },
  {
    title: "Caller",
    description:
      "Phone verification and booking calls via Twilio. Makes outbound calls to verify business info, make reservations, and confirm details.",
    category: "Communication",
    icon: "Phone",
    priceUsd: 5,
  },
  {
    title: "Hackathon",
    description:
      "Event discovery and automatic registration. Finds upcoming hackathons by time, location, topics, and mode.",
    category: "Events",
    icon: "Calendar",
    priceUsd: 3,
  },
  {
    title: "Trip Planner",
    description:
      "Group trip planning with confidence-based inference. Minimizes questions by learning from your profile and history.",
    category: "Travel",
    icon: "Map",
    priceUsd: 10,
  },
  {
    title: "Refund Claim",
    description:
      "Automates refund claims for delayed transport. Parses ticket emails, checks eligibility, generates and submits claims.",
    category: "Finance",
    icon: "Receipt",
    priceUsd: 8,
  },
  {
    title: "Gift Suggestion",
    description:
      "Personalized gift recommendations. Analyzes recipients, searches for creative ideas, and learns price comfort zones.",
    category: "Shopping",
    icon: "Gift",
    priceUsd: 3,
  },
  {
    title: "Restaurant Booker",
    description:
      "Find and book restaurant tables with minimal friction. Checks your calendar, searches nearby spots matching your preferences.",
    category: "Dining",
    icon: "UtensilsCrossed",
    priceUsd: 5,
  },
  {
    title: "Smart Shopper",
    description:
      "Deal finding with economic reasoning. Tracks price history, uses economic reasoning for buy/wait decisions, and sets alerts.",
    category: "Shopping",
    icon: "ShoppingCart",
    priceUsd: 5,
  },
];

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
        walletAddress: "0x000000000000000000000000000000000000dEaD",
      },
    }));

  for (let i = 0; i < agents.length; i++) {
    const a = agents[i];
    const id = i + 1;
    await prisma.agent.upsert({
      where: { id },
      update: {
        title: a.title,
        description: a.description,
        category: a.category,
        icon: a.icon,
        priceUsd: a.priceUsd,
      },
      create: {
        title: a.title,
        description: a.description,
        category: a.category,
        icon: a.icon,
        priceUsd: a.priceUsd,
        tags: a.category.toLowerCase(),
        network: "base-sepolia",
        ownerId: user.id,
      },
    });
  }

  console.log(`Seeded ${agents.length} agents for user ${user.email}`);
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
