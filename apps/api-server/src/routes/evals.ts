import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function evalRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.get('/', async (request, reply) => {
    const { task_id, skill_id, page = '1', limit = '20' } = request.query as Record<string, string>;
    const offset = (parseInt(page) - 1) * parseInt(limit);

    const conditions: string[] = [];
    const params: (string | number)[] = [];
    let paramIdx = 1;

    if (task_id) {
      conditions.push(`task_id = $${paramIdx++}`);
      params.push(task_id);
    }
    if (skill_id) {
      conditions.push(`skill_id = $${paramIdx++}`);
      params.push(skill_id);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(parseInt(limit), offset);

    const result = await pool.query(
      `SELECT * FROM eval_runs ${whereClause} ORDER BY created_at DESC LIMIT $${paramIdx++} OFFSET $${paramIdx++}`,
      params
    );

    return { success: true, data: result.rows };
  });

  app.get('/tasks/:taskId', async (request, reply) => {
    const { taskId } = request.params as { taskId: string };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/tasks/${taskId}/eval`);
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Failed to fetch task eval' };
    }
  });
}
