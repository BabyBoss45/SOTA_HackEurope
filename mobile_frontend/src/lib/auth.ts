import { createHash } from 'crypto';

const JWT_SECRET = process.env.JWT_SECRET || 'sota-dev-secret-change-in-production';

export interface SessionPayload {
  userId: number;
  walletAddress?: string;
  exp: number;
}

export function hashPassword(password: string): string {
  return createHash('sha256').update(`${password}${JWT_SECRET}`).digest('hex');
}

export function verifyPassword(password: string, hash: string): boolean {
  return hashPassword(password) === hash;
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
