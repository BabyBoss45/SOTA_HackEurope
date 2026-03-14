import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getCurrentUser } from "@/lib/auth";
import { getExplorerUrl } from "@/lib/contracts";

// ── Interfaces ───────────────────────────────────────────────

export interface Stage {
  id: string;
  name: string;
  description: string;
  status: "complete" | "in_progress" | "pending";
}

export interface TaskBid {
  id: string;
  agent: string;
  agentIcon: string;
  price: string;
  reputation: number;
  eta: string;
  timestamp: string;
}

export interface AdaptationInfo {
  confidence: number;
  successRate: number;
  commonFailures: Record<string, number>;
  strategy: string;
  similarTasksFound: number;
  reasoning: string;
}

export interface DashboardTask {
  id: string;
  jobId: string;
  title: string;
  description: string;
  status: "in_progress" | "collecting_bids" | "completed" | "failed";
  progress: number;
  agent: string;
  agentIcon: string;
  tags: string[];
  createdAt: string;
  stages: Stage[];
  bids: TaskBid[];
  adaptation?: AdaptationInfo;
}

export async function GET() {
  try {
    // Fetch marketplace jobs with ALL updates (no take limit)
    const jobs = await prisma.marketplaceJob.findMany({
      orderBy: { createdAt: 'desc' },
      include: {
        updates: {
          orderBy: { createdAt: 'desc' },
        },
      },
    });

    // Fetch all agents and build lookup maps
    const allAgents = await prisma.agent.findMany();
    const agentByTitle = new Map<string, typeof allAgents[0]>();
    const agentById = new Map<number, typeof allAgents[0]>();
    for (const a of allAgents) {
      agentByTitle.set(a.title.toLowerCase(), a);
      agentById.set(a.id, a);
    }

    // Also fetch agent data requests to show pending communications
    const dataRequests = await prisma.agentDataRequest.findMany({
      where: { status: 'pending' },
      orderBy: { createdAt: 'desc' },
    });

    // Program link (Solana — single program ID)
    const programId = process.env.NEXT_PUBLIC_PROGRAM_ID || "F6dYHixw4PB4qCEERCYP19BxzKpuLV6JbbWRMUYrRZLY";
    const contractLinks = {
      program: getExplorerUrl("address", programId),
    };

    // Transform jobs to dashboard format
    const tasks: DashboardTask[] = jobs.map((job) => {
      // Parse metadata for additional info
      const metadata = job.metadata as Record<string, unknown> || {};

      // Map job status to dashboard status
      let status: DashboardTask["status"] = "collecting_bids";

      switch (job.status) {
        case "open":
        case "selecting":
          status = "collecting_bids";
          break;
        case "assigned":
          status = "in_progress";
          break;
        case "completed":
          status = "completed";
          break;
        case "expired":
        case "cancelled":
          status = "failed";
          break;
        default:
          status = "collecting_bids";
      }

      // Get latest non-bid update for progress tracking
      const latestUpdate = job.updates?.find(u => u.status !== "bid_submitted");
      if (latestUpdate) {
        if (latestUpdate.status === "in_progress") {
          status = "in_progress";
        } else if (latestUpdate.status === "completed") {
          status = "completed";
        } else if (latestUpdate.status === "error") {
          status = "failed";
        }
      }

      // Extract real bids from updates
      const bidUpdates = (job.updates || []).filter(u => u.status === "bid_submitted");
      const bids: TaskBid[] = bidUpdates.map((u) => {
        const bidData = u.data as Record<string, unknown> || {};
        return {
          id: u.id.toString(),
          agent: u.agent,
          agentIcon: getAgentIcon(u.agent),
          price: `${Number(bidData.price_usdc ?? 0).toFixed(2)} USDC`,
          reputation: 90, // Default reputation; could be enriched later
          eta: `${Math.round(Number(bidData.eta_seconds || 0))}s`,
          timestamp: u.createdAt.toISOString(),
        };
      });

      // Generate stages based on task status
      const stages = generateStages(status, job.winner || "Agent", bids.length);

      // Parse adaptation update from task memory system
      let adaptation: AdaptationInfo | undefined;
      const adaptationUpdate = (job.updates || []).find(u => u.status === "adaptation");
      if (adaptationUpdate) {
        const ad = adaptationUpdate.data as Record<string, unknown> || {};
        adaptation = {
          confidence: Number(ad.confidence ?? 1),
          successRate: Number(ad.success_rate ?? 1),
          commonFailures: (ad.common_failures as Record<string, number>) || {},
          strategy: String(ad.strategy || "standard"),
          similarTasksFound: Number(ad.similar_tasks_found ?? 0),
          reasoning: String(adaptationUpdate.message || ""),
        };
      }

      return {
        id: job.id.toString(),
        jobId: job.jobId,
        title: generateTitle(job.description, job.tags),
        description: job.description,
        status,
        progress: 0,
        agent: job.winner || "Pending",
        agentIcon: getAgentIcon(job.winner),
        tags: job.tags || [],
        createdAt: job.createdAt instanceof Date ? job.createdAt.toISOString() : new Date(job.createdAt).toISOString(),
        stages,
        bids,
        adaptation,
      };
    });

    // Sort tasks: active first (collecting_bids, in_progress), then completed, then failed
    const priority: Record<string, number> = { collecting_bids: 0, in_progress: 1, completed: 2, failed: 3 };
    tasks.sort((a, b) => {
      const pa = priority[a.status] ?? 3;
      const pb = priority[b.status] ?? 3;
      if (pa !== pb) return pa - pb;
      return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
    });

    // Filter out failed/expired from visible task list
    const visibleTasks = tasks.filter(t => t.status !== "failed");

    // Group by status
    const in_progress = tasks.filter((t) => t.status === "in_progress");
    const collecting_bids = tasks.filter((t) => t.status === "collecting_bids");
    const completed = tasks.filter((t) => t.status === "completed");
    const failed = tasks.filter((t) => t.status === "failed");

    // Get online agents with extended info
    const activeAgents = allAgents.filter(
      (a) => a.status === "active" || a.status === "busy"
    );

    return NextResponse.json({
      tasks: visibleTasks,
      grouped: {
        in_progress,
        collecting_bids,
        completed,
        failed,
      },
      stats: {
        total: visibleTasks.length,
        in_progress: in_progress.length,
        collecting_bids: collecting_bids.length,
        completed: completed.length,
        failed: failed.length,
        pendingRequests: dataRequests.length,
      },
      agents: activeAgents.map((a) => ({
        id: a.id,
        title: a.title,
        status: a.status,
        icon: a.icon || "Bot",
        walletAddress: a.walletAddress,
        reputation: a.reputation ?? 0,
        isVerified: a.isVerified ?? false,
        explorerLink: a.walletAddress
          ? getExplorerUrl("address", a.walletAddress)
          : a.onchainAddress
            ? getExplorerUrl("address", a.onchainAddress)
            : null,
      })),
      contractLinks,
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    // Database unreachable — return empty state so the page loads cleanly
    if (
      msg.includes("Can't reach database") ||
      msg.includes("ECONNREFUSED") ||
      msg.includes("connect ETIMEDOUT") ||
      msg.includes("P1001")
    ) {
      const programId = process.env.NEXT_PUBLIC_PROGRAM_ID || "F6dYHixw4PB4qCEERCYP19BxzKpuLV6JbbWRMUYrRZLY";
      return NextResponse.json({
        tasks: [],
        grouped: { in_progress: [], collecting_bids: [], completed: [], failed: [] },
        stats: { total: 0, in_progress: 0, collecting_bids: 0, completed: 0, failed: 0, pendingRequests: 0 },
        agents: [],
        contractLinks: { program: getExplorerUrl("address", programId) },
        db_offline: true,
      });
    }
    console.error("Failed to fetch dashboard tasks:", error);
    return NextResponse.json(
      { error: "Failed to fetch tasks" },
      { status: 500 }
    );
  }
}

// Helper functions
function generateTitle(description: string, tags: string[]): string {
  if (tags && tags.length > 0) {
    const tag = tags[0];
    return tag
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }
  return description.length > 50
    ? description.substring(0, 50) + "..."
    : description;
}

function getAgentIcon(agentName: string | null): string {
  if (!agentName) return "Bot";
  const name = agentName.toLowerCase();
  if (name.includes("caller")) return "Phone";
  if (name.includes("hackathon")) return "Calendar";
  if (name.includes("manager")) return "Briefcase";
  return "Bot";
}

function generateStages(
  taskStatus: "in_progress" | "collecting_bids" | "completed" | "failed",
  agentName: string,
  bidCount: number,
): Stage[] {
  const stages: Stage[] = [
    {
      id: "collecting_bids",
      name: "Collecting Bids",
      description: bidCount > 0 ? `${bidCount} bid${bidCount !== 1 ? "s" : ""} received` : "Awaiting agent bids",
      status: "pending",
    },
    {
      id: "in_progress",
      name: "In Progress",
      description: agentName !== "Agent" ? `${agentName} executing` : "Agent executing task",
      status: "pending",
    },
    {
      id: "completed",
      name: "Completed",
      description: "Task finished",
      status: "pending",
    },
  ];

  if (taskStatus === "collecting_bids") {
    stages[0].status = "in_progress";
  } else if (taskStatus === "in_progress") {
    stages[0].status = "complete";
    stages[0].description = bidCount > 0 ? `${bidCount} bid${bidCount !== 1 ? "s" : ""} received` : "Bids collected";
    stages[1].status = "in_progress";
  } else if (taskStatus === "completed") {
    stages[0].status = "complete";
    stages[0].description = bidCount > 0 ? `${bidCount} bid${bidCount !== 1 ? "s" : ""} received` : "Bids collected";
    stages[1].status = "complete";
    stages[1].description = agentName !== "Agent" ? `${agentName} completed execution` : "Agent completed execution";
    stages[2].status = "complete";
    stages[2].description = "Task finished successfully";
  } else if (taskStatus === "failed") {
    stages[0].status = "complete";
    stages[0].description = "Bids collected";
    stages[1].status = agentName !== "Agent" ? "complete" : "pending";
    stages[1].description = agentName !== "Agent" ? `${agentName} was assigned` : "Agent selection attempted";
    stages[2].status = "pending";
    stages[2].description = "Task did not complete";
  }

  return stages;
}
