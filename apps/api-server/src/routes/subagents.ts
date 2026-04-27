import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function subagentRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.get('/', async (request, reply) => {
    const { task_id, role, status } = request.query as Record<string, string>;
    const conditions: string[] = [];
    const params: string[] = [];
    let paramIdx = 1;

    if (task_id) {
      conditions.push(`task_id = $${paramIdx++}`);
      params.push(task_id);
    }
    if (role) {
      conditions.push(`role = $${paramIdx++}`);
      params.push(role);
    }
    if (status) {
      conditions.push(`status = $${paramIdx++}`);
      params.push(status);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    const result = await pool.query(
      `SELECT * FROM subagents ${whereClause} ORDER BY created_at DESC`,
      params
    );
    return { success: true, data: result.rows };
  });

  app.get('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query('SELECT * FROM subagents WHERE id = $1', [id]);
    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Subagent not found' };
    }
    return { success: true, data: result.rows[0] };
  });

  app.post('/:id/analyze', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as Record<string, unknown>;

    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/tasks/${id}/subagents/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Subagent analysis failed' };
    }
  });
}
