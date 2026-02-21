import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { agentSchema } from "@/lib/validators";
import { getCurrentUser } from "@/lib/auth";

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const mine = searchParams.get("mine") === "true";

    // If ?mine=true, require auth and filter by ownerId
    if (mine) {
      const user = await getCurrentUser(req);
      if (!user) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
      }

      const agents = await prisma.agent.findMany({
        where: { ownerId: user.id },
      });

      // Sort by creation date descending
      agents.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

      const agentsWithOwner = agents.map((agent) => ({
        ...agent,
        owner: { id: user.id, email: user.email, name: user.name },
      }));

      return NextResponse.json({ agents: agentsWithOwner });
    }

    // Public listing — all agents
    const agents = await prisma.agent.findMany();

    // Sort by creation date descending
    agents.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

    const agentsWithOwner = await Promise.all(
      agents.map(async (agent) => {
        const owner = await prisma.user.findUnique({ where: { id: agent.ownerId } });
        return { ...agent, owner: owner ? { id: owner.id, email: owner.email, name: owner.name } : null };
      })
    );

    return NextResponse.json({ agents: agentsWithOwner });
  } catch (error) {
    console.error("Error fetching agents:", error);
    return NextResponse.json({ error: "Failed to fetch agents" }, { status: 500 });
  }
}

export async function POST(req: Request) {
  const user = await getCurrentUser(req);
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const parsed = agentSchema.safeParse({
    ...body,
    priceUsd: Number(body.priceUsd),
  });

  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.flatten().fieldErrors },
      { status: 400 },
    );
  }

  // Validate API endpoint if provided
  if (parsed.data.apiEndpoint) {
    try {
      const testUrl = new URL(parsed.data.apiEndpoint);
      if (!["http:", "https:"].includes(testUrl.protocol)) {
        return NextResponse.json(
          { error: "API endpoint must use HTTP or HTTPS protocol" },
          { status: 400 }
        );
      }
    } catch (error) {
      return NextResponse.json(
        { error: "Invalid API endpoint URL" },
        { status: 400 }
      );
    }
  }

  const agent = await prisma.agent.create({
    data: {
      ...parsed.data,
      ownerId: user.id,
      tags: parsed.data.tags ?? null,
      isVerified: false,
    },
  });

  return NextResponse.json({ agent });
}
