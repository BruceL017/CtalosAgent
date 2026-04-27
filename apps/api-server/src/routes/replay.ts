import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function replayRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.get('/', async (request, reply) => {
    const { task_id } = request.query as Record<string, string>;
    let query = 'SELECT * FROM replay_sessions';
    const params: string[] = [];
    if (task_id) {
      query += ' WHERE task_id = $1';
      params.push(task_id);
    }
    query += ' ORDER BY created_at DESC';
    const result = await pool.query(query, params);
    return { success: true, data: result.rows };
  });

  app.get('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query('SELECT * FROM replay_sessions WHERE id = $1', [id]);
    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Replay session not found' };
    }
    return { success: true, data: result.rows[0] };
  });

  app.post('/', async (request, reply) => {
    const body = request.body as {
      task_id: string;
      replay_type: string;
      from_sequence?: number;
      to_sequence?: number;
      speed?: string;
    };

    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/tasks/${body.task_id}/replay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Replay creation failed' };
    }
  });
}
