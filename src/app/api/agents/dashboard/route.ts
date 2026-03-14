import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export interface DashboardAgent {
  id: number;
  title: string;
  description: string;
  icon: string;
  status: "online" | "busy" | "offline";
  totalRequests: number;
  reputation: number;
  successRate: number;
  isButler: boolean;
}

export async function GET() {
  try {
    // Fetch portal agents from DB
    const dbAgents = await prisma.agent.findMany({
      orderBy: { createdAt: 'asc' },
    });

    // Transform portal agents to dashboard format
    const agents: DashboardAgent[] = dbAgents.map((agent) => {
      const totalReqs = (agent as { totalRequests?: number }).totalRequests ?? 0;
      const successReqs = (agent as { successfulRequests?: number }).successfulRequests ?? 0;
      const rep = (agent as { reputation?: number }).reputation ?? 5.0;
      const iconName = (agent as { icon?: string }).icon ?? "Bot";

      const successRate = totalReqs > 0
        ? Math.round((successReqs / totalReqs) * 1000) / 10
        : 100;

      // Determine status based on DB status field
      let status: "online" | "busy" | "offline" = "online";
      if (agent.status === "busy" || agent.status === "processing") {
        status = "busy";
      } else if (agent.status === "offline" || agent.status === "inactive") {
        status = "offline";
      }

      return {
        id: agent.id,
        title: agent.title,
        description: agent.description,
        icon: iconName,
        status,
        totalRequests: totalReqs,
        reputation: rep,
        successRate,
        isButler: agent.title.toLowerCase() === "butler",
      };
    });

    // Fetch worker agents from WorkerAgent table
    const dbWorkers = await prisma.workerAgent.findMany({
      orderBy: { createdAt: 'asc' },
    });

    // Transform WorkerAgent rows into DashboardAgent[]
    const workerDashboard: DashboardAgent[] = dbWorkers.map((w) => ({
      id: 100000 + w.id,  // offset to avoid ID collision with Agent table
      title: w.name,
      description: w.description || "",
      icon: w.icon || "Bot",
      status: (w.status === "online" ? "online" : w.status === "busy" ? "busy" : "offline") as "online" | "busy" | "offline",
      totalRequests: w.totalJobs,
      reputation: w.reputation,
      successRate: w.totalJobs > 0 ? Math.round((w.successfulJobs / w.totalJobs) * 1000) / 10 : 100,
      isButler: false,
    }));

    // Merge portal agents and worker agents, deduplicating by normalized title
    // e.g. "SOTA Hackathon Agent" and "Hackathon Agent" are the same agent
    const normalize = (t: string) => t.toLowerCase().replace(/^sota\s+/, '').replace(/\s+agent$/, '').trim();
    const portalKeys = new Set(agents.map(a => normalize(a.title)));
    const uniqueWorkers = workerDashboard.filter(w => !portalKeys.has(normalize(w.title)));
    const allAgents = [...agents, ...uniqueWorkers];

    // Separate Butler from other agents
    const butler = allAgents.find(a => a.isButler) || {
      id: 0,
      title: "Butler",
      description: "Your AI concierge orchestrating all agents",
      icon: "Bot",
      status: "online" as const,
      totalRequests: 0,
      reputation: 5.0,
      successRate: 100,
      isButler: true,
    };

    const workerAgents = allAgents.filter(a => !a.isButler);

    return NextResponse.json({
      butler,
      agents: workerAgents,
      total: allAgents.length,
    });
  } catch (error) {
    console.error("Failed to fetch dashboard agents:", error);
    return NextResponse.json(
      { error: "Failed to fetch agents" },
      { status: 500 }
    );
  }
}
