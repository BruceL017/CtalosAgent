import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function rollbackRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.get('/', async (request, reply) => {
    const { task_id, executed } = request.query as Record<string, string>;
    const conditions: string[] = [];
    const params: string[] = [];
    let paramIdx = 1;

    if (task_id) {
      conditions.push(`task_id = $${paramIdx++}`);
      params.push(task_id);
    }
    if (executed !== undefined) {
      conditions.push(`executed = $${paramIdx++}`);
      params.push(executed);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    const result = await pool.query(
      `SELECT * FROM rollback_plans ${whereClause} ORDER BY created_at DESC`,
      params
    );
    return { success: true, data: result.rows };
  });

  app.get('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query('SELECT * FROM rollback_plans WHERE id = $1', [id]);
    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Rollback plan not found' };
    }
    return { success: true, data: result.rows[0] };
  });

  app.post('/:id/execute', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as { executed_by?: string };

    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/rollback-plans/${id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ executed_by: body.executed_by || 'admin' }),
      });
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Rollback execution failed' };
    }
  });

  app.post('/:id/dry-run', async (request, reply) => {
    const { id } = request.params as { id: string };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/rollback-plans/${id}/dry-run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Rollback dry-run failed' };
    }
  });

  app.get('/executions', async (request, reply) => {
    const { plan_id } = request.query as Record<string, string>;
    const result = await pool.query(
      'SELECT * FROM rollback_executions WHERE rollback_plan_id = $1 ORDER BY created_at DESC',
      [plan_id]
    );
    return { success: true, data: result.rows };
  });
}
