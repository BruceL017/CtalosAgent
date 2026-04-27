import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';
import { v4 as uuidv4 } from 'uuid';

interface CreateTaskBody {
  title: string;
  description: string;
  risk_level?: string;
  environment?: string;
  skill_id?: string;
  context?: Record<string, unknown>;
}

interface UpdateTaskBody {
  status?: string;
  result?: Record<string, unknown>;
  error_message?: string;
}

export async function taskRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  // List tasks with pagination
  app.get('/', async (request, reply) => {
    const { page = '1', limit = '20', status } = request.query as Record<string, string>;
    const offset = (parseInt(page) - 1) * parseInt(limit);

    let whereClause = '';
    const params: (string | number)[] = [parseInt(limit), offset];
    if (status) {
      whereClause = 'WHERE status = $3';
      params.push(status);
    }

    const result = await pool.query(
      `SELECT * FROM tasks ${whereClause} ORDER BY created_at DESC LIMIT $1 OFFSET $2`,
      params
    );

    const countResult = await pool.query(
      `SELECT COUNT(*) FROM tasks ${whereClause}`,
      status ? [status] : []
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

  // Get single task
  app.get('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query('SELECT * FROM tasks WHERE id = $1', [id]);

    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Task not found' };
    }

    return { success: true, data: result.rows[0] };
  });

  // Create task
  app.post('/', async (request, reply) => {
    const body = request.body as CreateTaskBody;
    const id = uuidv4();

    const result = await pool.query(
      `INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by, skill_id, context)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
       RETURNING *`,
      [
        id,
        body.title,
        body.description,
        'pending',
        body.risk_level || 'low',
        body.environment || 'test',
        '00000000-0000-0000-0000-000000000001',
        body.skill_id || null,
        JSON.stringify(body.context || {}),
      ]
    );

    reply.status(201);
    return { success: true, data: result.rows[0] };
  });

  // Update task
  app.patch('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as UpdateTaskBody;

    const updates: string[] = [];
    const values: unknown[] = [];
    let paramIndex = 1;

    if (body.status) {
      updates.push(`status = $${paramIndex++}`);
      values.push(body.status);
      if (body.status === 'running') {
        updates.push(`started_at = NOW()`);
      }
      if (body.status === 'completed' || body.status === 'failed') {
        updates.push(`completed_at = NOW()`);
      }
    }
    if (body.result !== undefined) {
      updates.push(`result = $${paramIndex++}`);
      values.push(JSON.stringify(body.result));
    }
    if (body.error_message !== undefined) {
      updates.push(`error_message = $${paramIndex++}`);
      values.push(body.error_message);
    }

    if (updates.length === 0) {
      reply.status(400);
      return { success: false, error: 'No fields to update' };
    }

    updates.push(`updated_at = NOW()`);
    values.push(id);

    const result = await pool.query(
      `UPDATE tasks SET ${updates.join(', ')} WHERE id = $${paramIndex} RETURNING *`,
      values
    );

    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Task not found' };
    }

    return { success: true, data: result.rows[0] };
  });

  // Get task events
  app.get('/:id/events', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query(
      'SELECT * FROM task_events WHERE task_id = $1 ORDER BY sequence ASC',
      [id]
    );
    return { success: true, data: result.rows };
  });

  // Get task tool calls
  app.get('/:id/tool-calls', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query(
      'SELECT * FROM tool_calls WHERE task_id = $1 ORDER BY created_at ASC',
      [id]
    );
    return { success: true, data: result.rows };
  });

  // Trigger agent execution (POST to runtime)
  app.post('/:id/execute', async (request, reply) => {
    const { id } = request.params as { id: string };

    const taskResult = await pool.query('SELECT * FROM tasks WHERE id = $1', [id]);
    if (taskResult.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Task not found' };
    }

    const task = taskResult.rows[0];

    await pool.query(
      `UPDATE tasks SET status = 'running', started_at = NOW(), updated_at = NOW() WHERE id = $1`,
      [id]
    );

    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: id, task }),
      });

      const data = await response.json();
      return { success: true, data };
    } catch (err) {
      await pool.query(
        `UPDATE tasks SET status = 'failed', error_message = $1, updated_at = NOW() WHERE id = $2`,
        [`Failed to reach agent runtime: ${(err as Error).message}`, id]
      );
      reply.status(500);
      return { success: false, error: 'Agent runtime unreachable' };
    }
  });

  app.post('/:id/cancel', async (request, reply) => {
    const { id } = request.params as { id: string };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/tasks/${id}/cancel`, { method: 'POST' });
      const data = await response.json();
      return data;
    } catch (err) {
      await pool.query("UPDATE tasks SET status = 'cancelled', updated_at = NOW() WHERE id = $1", [id]);
      return { success: true, task_id: id, status: 'cancelled' };
    }
  });

  app.post('/:id/pause', async (request, reply) => {
    const { id } = request.params as { id: string };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/tasks/${id}/pause`, { method: 'POST' });
      const data = await response.json();
      return data;
    } catch (err) {
      await pool.query("UPDATE tasks SET status = 'paused', updated_at = NOW() WHERE id = $1", [id]);
      return { success: true, task_id: id, status: 'paused' };
    }
  });

  app.post('/:id/resume', async (request, reply) => {
    const { id } = request.params as { id: string };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/tasks/${id}/resume`, { method: 'POST' });
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Failed to resume task' };
    }
  });

  app.post('/:id/rollback', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as { executed_by?: string };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/tasks/${id}/rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ executed_by: body?.executed_by || 'admin' }),
      });
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Rollback failed' };
    }
  });

  app.post('/:id/subagents', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as { roles?: string[]; task_context?: Record<string, unknown> };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/tasks/${id}/subagents/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          roles: body.roles || ['product', 'dev', 'ops'],
          task_context: body.task_context || {},
        }),
      });
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Subagent analysis failed' };
    }
  });
}
