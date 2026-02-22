/* eslint-disable @typescript-eslint/no-require-imports */
// Simple seed script to create a demo user and sample agents
require("dotenv").config();
const { PrismaClient } = require("@prisma/client");
const { createHash } = require("crypto");

const prisma = new PrismaClient();

async function main() {
  const existing = await prisma.user.findUnique({
    where: { email: "demo@sota.ai" },
  });

  const JWT_SECRET = process.env.JWT_SECRET || 'sota-dev-secret-change-in-production';
  const passwordHash = createHash('sha256').update(`password123${JWT_SECRET}`).digest('hex');

  const user = existing
    ? await prisma.user.update({
        where: { email: "demo@sota.ai" },
        data: { passwordHash },
      })
    : await prisma.user.create({
        data: {
          email: "demo@sota.ai",
          name: "Demo User",
          passwordHash,
          walletAddress: "11111111111111111111111111111111",
        },
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

