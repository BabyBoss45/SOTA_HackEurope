import { z } from "zod";

export const authSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6, "Password must be at least 6 characters"),
  name: z.string().min(2, "Name is required").optional(),
});

export const agentSchema = z.object({
  title: z.string().min(3),
  description: z.string().min(10),
  category: z.string().optional(),
  priceUsd: z.number().min(0),
  tags: z.string().optional(),
  network: z.string().optional(),
  // Developer portal fields
  apiEndpoint: z.string().url().optional(),
  apiKey: z.string().optional(),
  capabilities: z.string().optional(), // JSON stringified array
  webhookUrl: z.string().url().optional(),
  documentation: z.string().optional(),
});

export const profileSchema = z.object({
  walletAddress: z
    .string()
    .regex(/^[1-9A-HJ-NP-Za-km-z]{32,44}$/, "Must be a valid Solana address")
    .optional(),
  name: z.string().min(2).optional(),
});

export type AuthPayload = z.infer<typeof authSchema>;
export type AgentPayload = z.infer<typeof agentSchema>;
export type ProfilePayload = z.infer<typeof profileSchema>;

