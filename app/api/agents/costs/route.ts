import { NextResponse } from "next/server";

const PAID_API_BASE = "https://api.agentpaid.io/api/v2";

interface PaidProduct {
  id: string;
  name: string;
  external_id: string;
}

interface PaidTransaction {
  id: string;
  amount: number;
  cost: number;
  created_at: string;
  product_id: string;
}

interface AgentCostData {
  name: string;
  externalId: string;
  revenue: number;
  cost: number;
  profit: number;
  jobCount: number;
}

async function paidFetch<T>(path: string, apiKey: string): Promise<T | null> {
  try {
    const res = await fetch(`${PAID_API_BASE}${path}`, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function GET() {
  const apiKey = process.env.SOTA_PAID_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "SOTA_PAID_API_KEY not configured" },
      { status: 503 }
    );
  }

  try {
    // Fetch all products from Paid.ai
    const products = await paidFetch<PaidProduct[]>("/products", apiKey);
    if (!products) {
      return NextResponse.json(
        { error: "Failed to fetch products from Paid.ai" },
        { status: 502 }
      );
    }

    // Fetch transactions for each product
    const agents: AgentCostData[] = [];
    let totalRevenue = 0;
    let totalCost = 0;
    let totalJobs = 0;

    for (const product of products) {
      const transactions = await paidFetch<PaidTransaction[]>(
        `/products/${product.id}/transactions`,
        apiKey
      );

      let revenue = 0;
      let cost = 0;
      let jobCount = 0;

      if (transactions && Array.isArray(transactions)) {
        for (const tx of transactions) {
          revenue += tx.amount ?? 0;
          cost += tx.cost ?? 0;
          jobCount++;
        }
      }

      agents.push({
        name: product.name,
        externalId: product.external_id,
        revenue: Math.round(revenue * 100) / 100,
        cost: Math.round(cost * 10000) / 10000,
        profit: Math.round((revenue - cost) * 100) / 100,
        jobCount,
      });

      totalRevenue += revenue;
      totalCost += cost;
      totalJobs += jobCount;
    }

    return NextResponse.json({
      agents,
      totals: {
        revenue: Math.round(totalRevenue * 100) / 100,
        cost: Math.round(totalCost * 10000) / 10000,
        profit: Math.round((totalRevenue - totalCost) * 100) / 100,
        jobCount: totalJobs,
      },
    });
  } catch (error) {
    console.error("Failed to fetch Paid.ai cost data:", error);
    return NextResponse.json(
      { error: "Failed to fetch cost data" },
      { status: 500 }
    );
  }
}
