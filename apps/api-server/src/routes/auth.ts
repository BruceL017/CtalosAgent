import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';
import { generateJWT, hashPassword, verifyPassword } from '../middleware/auth.js';

// In-memory admin for MVP (hashed password via PBKDF2)
// Production should use DB-backed users with bcrypt
const DEFAULT_ADMIN = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'admin@enterprise.local',
  role: 'admin',
};

// Generate hash on module load so default password works
const DEFAULT_PASSWORD = process.env.DEFAULT_ADMIN_PASSWORD || 'admin123';
const DEFAULT_ADMIN_HASH = hashPassword(DEFAULT_PASSWORD);

export async function authRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.post('/login', async (request, reply) => {
    const body = request.body as { email?: string; password?: string };
    const { email, password } = body;

    if (!email || !password) {
      reply.status(400);
      return { success: false, error: 'Email and password required' };
    }

    // Check default admin
    if (email === DEFAULT_ADMIN.email) {
      if (verifyPassword(password, DEFAULT_ADMIN_HASH)) {
        const token = generateJWT(DEFAULT_ADMIN.id, DEFAULT_ADMIN.email, DEFAULT_ADMIN.role);
        return {
          success: true,
          data: {
            token,
            user: { id: DEFAULT_ADMIN.id, email: DEFAULT_ADMIN.email, role: DEFAULT_ADMIN.role },
          },
        };
      }
    }

    // Check DB users
    try {
      const result = await pool.query(
        'SELECT id, email, role, password_hash FROM users WHERE email = $1 AND is_active = TRUE',
        [email]
      );
      const user = result.rows[0];
      if (!user) {
        reply.status(401);
        return { success: false, error: 'Invalid credentials' };
      }

      // Production: PBKDF2 verify
      // MVP fallback: if stored hash doesn't contain ':', treat as legacy plaintext
      let passwordValid = false;
      if (user.password_hash && user.password_hash.includes(':')) {
        passwordValid = verifyPassword(password, user.password_hash);
      } else {
        passwordValid = user.password_hash === password;
      }

      if (!passwordValid) {
        reply.status(401);
        return { success: false, error: 'Invalid credentials' };
      }

      const token = generateJWT(user.id, user.email, user.role);
      return {
        success: true,
        data: {
          token,
          user: { id: user.id, email: user.email, role: user.role },
        },
      };
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Login failed' };
    }
  });

  app.get('/me', async (request, reply) => {
    const user = (request as any).user;
    if (!user) {
      reply.status(401);
      return { success: false, error: 'Unauthorized' };
    }
    return { success: true, data: user };
  });
}
