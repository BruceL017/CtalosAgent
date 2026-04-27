import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function skillRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  // List skills
  app.get('/', async (request, reply) => {
    const { domain, status } = request.query as Record<string, string>;
    const conditions: string[] = [];
    const params: string[] = [];
    let paramIndex = 1;

    if (domain) {
      conditions.push(`domain = $${paramIndex++}`);
      params.push(domain);
    }
    if (status) {
      conditions.push(`status = $${paramIndex++}`);
      params.push(status);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    const result = await pool.query(
      `SELECT * FROM skills ${whereClause} ORDER BY updated_at DESC`,
      params
    );
    return { success: true, data: result.rows };
  });

  // Get single skill
  app.get('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query('SELECT * FROM skills WHERE id = $1', [id]);

    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Skill not found' };
    }

    return { success: true, data: result.rows[0] };
  });

  // Get skill versions
  app.get('/:id/versions', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query(
      'SELECT * FROM skill_versions WHERE skill_id = $1 ORDER BY created_at DESC',
      [id]
    );
    return { success: true, data: result.rows };
  });
}
