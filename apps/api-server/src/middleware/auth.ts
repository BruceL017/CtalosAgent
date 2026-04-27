/**
 * Auth Middleware: JWT validation + minimal RBAC + PBKDF2 password hashing
 * Roles: admin, operator, viewer
 */
import type { FastifyRequest, FastifyReply } from 'fastify';
import { createHmac, pbkdf2Sync, randomBytes } from 'crypto';

const JWT_SECRET = process.env.JWT_SECRET || 'change-this-to-a-random-string-at-least-32-chars';

interface JWTPayload {
  userId: string;
  email: string;
  role: string;
  iat: number;
  exp: number;
}

// Password hashing with PBKDF2 (Node.js built-in, no extra deps)
export function hashPassword(password: string): string {
  const salt = randomBytes(16).toString('hex');
  const hash = pbkdf2Sync(password, salt, 10000, 64, 'sha512').toString('hex');
  return `${salt}:${hash}`;
}

export function verifyPassword(password: string, stored: string): boolean {
  const parts = stored.split(':');
  if (parts.length !== 2) return false;
  const [salt, hash] = parts;
  const verifyHash = pbkdf2Sync(password, salt, 10000, 64, 'sha512').toString('hex');
  return hash === verifyHash;
}

function base64UrlDecode(str: string): string {
  const padding = '='.repeat((4 - (str.length % 4)) % 4);
  return Buffer.from(str.replace(/-/g, '+').replace(/_/g, '/') + padding, 'base64').toString('utf8');
}

function verifyJWT(token: string): JWTPayload | null {
  try {
    const [header, payload, signature] = token.split('.');
    if (!header || !payload || !signature) return null;

    const expectedSig = createHmac('sha256', JWT_SECRET)
      .update(`${header}.${payload}`)
      .digest('base64url');
    if (expectedSig !== signature) return null;

    const data = JSON.parse(base64UrlDecode(payload)) as JWTPayload;
    if (data.exp && data.exp < Math.floor(Date.now() / 1000)) return null;
    return data;
  } catch {
    return null;
  }
}

export function generateJWT(userId: string, email: string, role: string, expiresInHours = 24): string {
  const header = JSON.stringify({ alg: 'HS256', typ: 'JWT' });
  const iat = Math.floor(Date.now() / 1000);
  const payload = JSON.stringify({ userId, email, role, iat, exp: iat + expiresInHours * 3600 });

  const encodedHeader = Buffer.from(header).toString('base64url');
  const encodedPayload = Buffer.from(payload).toString('base64url');
  const signature = createHmac('sha256', JWT_SECRET)
    .update(`${encodedHeader}.${encodedPayload}`)
    .digest('base64url');

  return `${encodedHeader}.${encodedPayload}.${signature}`;
}

export async function authMiddleware(request: FastifyRequest, reply: FastifyReply) {
  const authHeader = request.headers.authorization || '';
  const token = authHeader.replace('Bearer ', '');

  if (!token) {
    reply.status(401).send({ success: false, error: 'Unauthorized: no token provided' });
    return;
  }

  const payload = verifyJWT(token);
  if (!payload) {
    reply.status(401).send({ success: false, error: 'Unauthorized: invalid or expired token' });
    return;
  }

  // Attach user info to request
  (request as any).user = payload;
}

export function requireRole(...roles: string[]) {
  return async (request: FastifyRequest, reply: FastifyReply) => {
    const user = (request as any).user;
    if (!user) {
      reply.status(401);
      return { success: false, error: 'Unauthorized' };
    }
    if (!roles.includes(user.role)) {
      reply.status(403);
      return { success: false, error: `Forbidden: requires role ${roles.join(' or ')}` };
    }
  };
}

export { verifyJWT };
