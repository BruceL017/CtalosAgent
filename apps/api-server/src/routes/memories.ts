import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function memoryRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.get('/', async (request, reply) => {
    const { type, scope, search, page = '1', limit = '20' } = request.query as Record<string, string>;
    const offset = (parseInt(page) - 1) * parseInt(limit);

    const conditions: string[] = [];
    const params: (string | number)[] = [];
    let paramIdx = 1;

    if (type) {
      conditions.push(`memory_type = $${paramIdx++}`);
      params.push(type);
    }
    if (scope) {
      conditions.push(`scope = $${paramIdx++}`);
      params.push(scope);
    }
    if (search) {
      conditions.push(`content ILIKE $${paramIdx++}`);
      params.push(`%${search}%`);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(parseInt(limit), offset);

    const result = await pool.query(
      `SELECT * FROM memories ${whereClause} ORDER BY updated_at DESC LIMIT $${paramIdx++} OFFSET $${paramIdx++}`,
      params
    );

    const countResult = await pool.query(
      `SELECT COUNT(*) FROM memories ${whereClause}`,
      params.slice(0, -2)
    );

    return {
      success: true,
      data: result.rows,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total: parseInt(countResult.rows[0].count),
      },
    };
  });

  app.get('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query('SELECT * FROM memories WHERE id = $1', [id]);
    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Memory not found' };
    }
    return { success: true, data: result.rows[0] };
  });

  app.patch('/:id/deactivate', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query(
      'UPDATE memories SET is_active = FALSE, updated_at = NOW() WHERE id = $1 RETURNING *',
      [id]
    );
    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Memory not found' };
    }
    return { success: true, data: result.rows[0] };
  });

  app.get('/:id/similar', async (request, reply) => {
    const { id } = request.params as { id: string };
    const { limit = '5' } = request.query as Record<string, string>;

    const memory = await pool.query('SELECT content FROM memories WHERE id = $1', [id]);
    if (memory.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Memory not found' };
    }

    // Text-based similar search for MVP
    const result = await pool.query(
      'SELECT * FROM memories WHERE id != $1 AND content ILIKE $2 AND is_active = TRUE LIMIT $3',
      [id, `%${memory.rows[0].content.substring(0, 50)}%`, parseInt(limit)]
    );
    return { success: true, data: result.rows };
  });
}
