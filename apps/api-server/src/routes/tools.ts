import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function toolRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  // List tool calls
  app.get('/calls', async (request, reply) => {
    const { task_id, tool_name, status, page = '1', limit = '20' } = request.query as Record<string, string>;
    const offset = (parseInt(page) - 1) * parseInt(limit);

    const conditions: string[] = [];
    const params: (string | number)[] = [];
    let paramIndex = 1;

    if (task_id) {
      conditions.push(`task_id = $${paramIndex++}`);
      params.push(task_id);
    }
    if (tool_name) {
      conditions.push(`tool_name = $${paramIndex++}`);
      params.push(tool_name);
    }
    if (status) {
      conditions.push(`status = $${paramIndex++}`);
      params.push(status);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(parseInt(limit), offset);

    const result = await pool.query(
      `SELECT * FROM tool_calls ${whereClause} ORDER BY created_at DESC LIMIT $${paramIndex++} OFFSET $${paramIndex++}`,
      params
    );

    return { success: true, data: result.rows };
  });
}
