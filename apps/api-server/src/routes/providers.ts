import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function providerRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.get('/', async (request, reply) => {
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/providers`);
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Failed to fetch providers' };
    }
  });

  app.get('/health', async (request, reply) => {
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/providers/health`);
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Failed to fetch provider health' };
    }
  });

  app.get('/stats', async (request, reply) => {
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/providers/stats`);
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Failed to fetch provider stats' };
    }
  });

  app.get('/metrics', async (request, reply) => {
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/metrics`);
      const text = await response.text();
      reply.header('Content-Type', 'text/plain; charset=utf-8');
      return text;
    } catch (err) {
      reply.status(500);
      return '# metrics unavailable\n';
    }
  });

  app.get('/configs', async (request, reply) => {
    const result = await pool.query('SELECT * FROM provider_configs ORDER BY fallback_order ASC');
    return { success: true, data: result.rows };
  });

  app.patch('/configs/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as Record<string, unknown>;

    const updates: string[] = [];
    const values: unknown[] = [];
    let paramIndex = 1;

    const allowedFields = ['model', 'is_active', 'is_default', 'fallback_order', 'timeout_seconds', 'max_retries'];
    for (const field of allowedFields) {
      if (field in body) {
        updates.push(`${field} = $${paramIndex++}`);
        values.push(body[field]);
      }
    }

    if (updates.length === 0) {
      reply.status(400);
      return { success: false, error: 'No fields to update' };
    }

    updates.push('updated_at = NOW()');
    values.push(id);

    const result = await pool.query(
      `UPDATE provider_configs SET ${updates.join(', ')} WHERE id = $${paramIndex} RETURNING *`,
      values
    );

    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Provider config not found' };
    }

    return { success: true, data: result.rows[0] };
  });
}
