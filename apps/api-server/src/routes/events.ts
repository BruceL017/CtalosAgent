import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function eventRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  // Get events with optional filters
  app.get('/', async (request, reply) => {
    const { task_id, event_type, page = '1', limit = '50' } = request.query as Record<string, string>;
    const offset = (parseInt(page) - 1) * parseInt(limit);

    const conditions: string[] = [];
    const params: (string | number)[] = [];
    let paramIndex = 1;

    if (task_id) {
      conditions.push(`task_id = $${paramIndex++}`);
      params.push(task_id);
    }
    if (event_type) {
      conditions.push(`event_type = $${paramIndex++}`);
      params.push(event_type);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(parseInt(limit), offset);

    const result = await pool.query(
      `SELECT * FROM task_events ${whereClause} ORDER BY created_at DESC LIMIT $${paramIndex++} OFFSET $${paramIndex++}`,
      params
    );

    return { success: true, data: result.rows };
  });

  // Get single event
  app.get('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query('SELECT * FROM task_events WHERE id = $1', [id]);

    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Event not found' };
    }

    return { success: true, data: result.rows[0] };
  });
}
