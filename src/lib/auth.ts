import { createHash, randomBytes, createCipheriv, createDecipheriv } from 'crypto';
import { prisma } from './prisma';
import type { Agent, User } from '@prisma/client';

const JWT_SECRET = process.env.JWT_SECRET || 'sota-dev-secret-change-in-production';
const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY || '0123456789abcdef0123456789abcdef'; // 32 bytes for AES-256

// ═══════════════════════════════════════════════════════════
//  API Key Generation & Validation
// ═══════════════════════════════════════════════════════════

export interface GeneratedApiKey {
  keyId: string;
  fullKey: string;
  keyHash: string;
}

export interface ValidatedApiKey {
  agent: Agent & { owner: User };
  owner: User;
  permissions: string[];
}

export function generateApiKey(): GeneratedApiKey {
  const keyId = `ak_${randomBytes(8).toString('hex')}`;
  const secret = randomBytes(24).toString('hex');
  const fullKey = `${keyId}.${secret}`;
  const keyHash = createHash('sha256').update(fullKey).digest('hex');

  return { keyId, fullKey, keyHash };
}

export async function validateApiKey(fullKey: string): Promise<ValidatedApiKey | null> {
  if (!fullKey || !fullKey.includes('.')) {
    return null;
  }

  const keyHash = createHash('sha256').update(fullKey).digest('hex');

  const apiKey = await prisma.agentApiKey.findFirst({
    where: {
      keyHash,
      isActive: true,
      OR: [
        { expiresAt: null },
        { expiresAt: { gt: new Date() } }
      ]
    },
    include: {
      agent: {
        include: { owner: true }
      }
    }
  });

  if (!apiKey) {
    return null;
  }

  // Update last used timestamp (fire-and-forget is fine here)
  await prisma.agentApiKey.update({
    where: { id: apiKey.id },
    data: { lastUsedAt: new Date() },
  });

  return {
    agent: apiKey.agent,
    owner: apiKey.agent.owner,
    permissions: apiKey.permissions,
  };
}

// ═══════════════════════════════════════════════════════════
//  Encryption for storing third-party API keys
// ═══════════════════════════════════════════════════════════

export function encryptApiKey(plainText: string): string {
  const iv = randomBytes(16);
  const cipher = createCipheriv('aes-256-cbc', Buffer.from(ENCRYPTION_KEY, 'utf-8'), iv);
  let encrypted = cipher.update(plainText, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  return `${iv.toString('hex')}:${encrypted}`;
}

export function decryptApiKey(encrypted: string): string {
  const [ivHex, encryptedText] = encrypted.split(':');
  const iv = Buffer.from(ivHex, 'hex');
  const decipher = createDecipheriv('aes-256-cbc', Buffer.from(ENCRYPTION_KEY, 'utf-8'), iv);
  let decrypted = decipher.update(encryptedText, 'hex', 'utf8');
  decrypted += decipher.final('utf8');
  return decrypted;
}

// ═══════════════════════════════════════════════════════════
//  Session Management (Simple JWT-like tokens)
// ═══════════════════════════════════════════════════════════

export interface SessionPayload {
  userId: number;
  walletAddress?: string;
  exp: number;
}

export function createSessionToken(payload: Omit<SessionPayload, 'exp'>): string {
  const exp = Date.now() + 7 * 24 * 60 * 60 * 1000; // 7 days
  const data = JSON.stringify({ ...payload, exp });
  const signature = createHash('sha256').update(`${data}${JWT_SECRET}`).digest('hex');
  return Buffer.from(`${data}.${signature}`).toString('base64');
}

export function verifySessionToken(token: string): SessionPayload | null {
  try {
    const decoded = Buffer.from(token, 'base64').toString('utf-8');
    const [data, signature] = decoded.split(/\.(?=[^.]+$)/); // Split on last dot
    
    const expectedSignature = createHash('sha256').update(`${data}${JWT_SECRET}`).digest('hex');
    if (signature !== expectedSignature) {
      return null;
    }
    
    const payload = JSON.parse(data) as SessionPayload;
    if (payload.exp < Date.now()) {
      return null;
    }
    
    return payload;
  } catch {
    return null;
  }
}

// ═══════════════════════════════════════════════════════════
//  Request Authentication Helpers
// ═══════════════════════════════════════════════════════════

export async function getCurrentUser(request: Request): Promise<User | null> {
  const authHeader = request.headers.get('Authorization');

  if (!authHeader) {
    return null;
  }

  if (authHeader.startsWith('Bearer ')) {
    const payload = verifySessionToken(authHeader.slice(7));
    if (!payload) return null;
    return prisma.user.findUnique({ where: { id: payload.userId } });
  }

  if (authHeader.startsWith('ApiKey ')) {
    const result = await validateApiKey(authHeader.slice(7));
    return result?.owner ?? null;
  }

  return null;
}

export async function requireAuth(request: Request): Promise<User> {
  const user = await getCurrentUser(request);

  if (!user) {
    throw new Error('Unauthorized');
  }

  return user;
}

export async function requireApiKeyAuth(
  request: Request,
  requiredPermission?: string,
): Promise<ValidatedApiKey> {
  const authHeader = request.headers.get('Authorization');

  if (!authHeader?.startsWith('ApiKey ')) {
    throw new AuthError('API key required', 401);
  }

  const result = await validateApiKey(authHeader.slice(7));
  if (!result) {
    throw new AuthError('Invalid API key', 401);
  }

  if (requiredPermission && !result.permissions.includes(requiredPermission)) {
    throw new AuthError(`API key does not have ${requiredPermission} permission`, 403);
  }

  return result;
}

export class AuthError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

// ═══════════════════════════════════════════════════════════
//  Wallet & Password Utilities
// ═══════════════════════════════════════════════════════════

export function generateNonce(): string {
  return `Sign this message to authenticate with SOTA:\n\nNonce: ${randomBytes(16).toString('hex')}\nTimestamp: ${Date.now()}`;
}

export function hashPassword(password: string): string {
  return createHash('sha256').update(`${password}${JWT_SECRET}`).digest('hex');
}

export function verifyPassword(password: string, hash: string): boolean {
  return hashPassword(password) === hash;
}
