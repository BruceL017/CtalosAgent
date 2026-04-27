import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';
import { v4 as uuidv4 } from 'uuid';

interface CreateSessionBody {
  title: string;
  description?: string;
  context?: Record<string, unknown>;
}

interface CreateMessageBody {
  role: string;
  content: string;
  tool_calls?: unknown[];
  tool_call_id?: string;
  metadata?: Record<string, unknown>;
}

interface CreateTaskFromSessionBody {
  title: string;
  description: string;
  risk_level?: string;
  environment?: string;
  skill_id?: string;
  context?: Record<string, unknown>;
}

export async function sessionRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  // List sessions with pagination
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
      `SELECT * FROM sessions ${whereClause} ORDER BY updated_at DESC LIMIT $1 OFFSET $2`,
      params
    );

    const countResult = await pool.query(
      `SELECT COUNT(*) FROM sessions ${whereClause}`,
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

  // Get single session with messages and linked tasks
  app.get('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };

    const sessionResult = await pool.query('SELECT * FROM sessions WHERE id = $1', [id]);
    if (sessionResult.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Session not found' };
    }

    const messagesResult = await pool.query(
      'SELECT * FROM session_messages WHERE session_id = $1 ORDER BY created_at ASC',
      [id]
    );

    const tasksResult = await pool.query(
      `SELECT t.* FROM tasks t
       JOIN session_task_links stl ON t.id = stl.task_id
       WHERE stl.session_id = $1
       ORDER BY t.created_at DESC`,
      [id]
    );

    return {
      success: true,
      data: {
        ...sessionResult.rows[0],
        messages: messagesResult.rows,
        tasks: tasksResult.rows,
      },
    };
  });

  // Create session
  app.post('/', async (request, reply) => {
    const body = request.body as CreateSessionBody;
    const id = uuidv4();

    const result = await pool.query(
      `INSERT INTO sessions (id, title, description, status, created_by, context)
       VALUES ($1, $2, $3, $4, $5, $6)
       RETURNING *`,
      [
        id,
        body.title,
        body.description || '',
        'active',
        '00000000-0000-0000-0000-000000000001',
        JSON.stringify(body.context || {}),
      ]
    );

    reply.status(201);
    return { success: true, data: result.rows[0] };
  });

  // Update session
  app.patch('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as Partial<CreateSessionBody> & { status?: string };

    const updates: string[] = [];
    const values: unknown[] = [];
    let paramIndex = 1;

    if (body.title !== undefined) {
      updates.push(`title = $${paramIndex++}`);
      values.push(body.title);
    }
    if (body.description !== undefined) {
      updates.push(`description = $${paramIndex++}`);
      values.push(body.description);
    }
    if (body.status !== undefined) {
      updates.push(`status = $${paramIndex++}`);
      values.push(body.status);
      if (body.status === 'ended') {
        updates.push(`ended_at = NOW()`);
      }
    }
    if (body.context !== undefined) {
      updates.push(`context = $${paramIndex++}`);
      values.push(JSON.stringify(body.context));
    }

    if (updates.length === 0) {
      reply.status(400);
      return { success: false, error: 'No fields to update' };
    }

    updates.push(`updated_at = NOW()`);
    values.push(id);

    const result = await pool.query(
      `UPDATE sessions SET ${updates.join(', ')} WHERE id = $${paramIndex} RETURNING *`,
      values
    );

    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Session not found' };
    }

    return { success: true, data: result.rows[0] };
  });

  // Add message to session
  app.post('/:id/messages', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as CreateMessageBody;

    // Verify session exists
    const sessionResult = await pool.query('SELECT id FROM sessions WHERE id = $1', [id]);
    if (sessionResult.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Session not found' };
    }

    const messageId = uuidv4();
    const result = await pool.query(
      `INSERT INTO session_messages (id, session_id, role, content, tool_calls, tool_call_id, metadata)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       RETURNING *`,
      [
        messageId,
        id,
        body.role,
        body.content,
        JSON.stringify(body.tool_calls || []),
        body.tool_call_id || null,
        JSON.stringify(body.metadata || {}),
      ]
    );

    // Update session updated_at
    await pool.query('UPDATE sessions SET updated_at = NOW() WHERE id = $1', [id]);

    reply.status(201);
    return { success: true, data: result.rows[0] };
  });

  // Get session messages
  app.get('/:id/messages', async (request, reply) => {
    const { id } = request.params as { id: string };
    const { limit = '50' } = request.query as Record<string, string>;

    const result = await pool.query(
      'SELECT * FROM session_messages WHERE session_id = $1 ORDER BY created_at ASC LIMIT $2',
      [id, parseInt(limit)]
    );

    return { success: true, data: result.rows };
  });

  // Create task from session
  app.post('/:id/tasks', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as CreateTaskFromSessionBody;

    // Verify session exists
    const sessionResult = await pool.query('SELECT id FROM sessions WHERE id = $1', [id]);
    if (sessionResult.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Session not found' };
    }

    const taskId = uuidv4();
    const taskResult = await pool.query(
      `INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by, skill_id, context, session_id)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
       RETURNING *`,
      [
        taskId,
        body.title,
        body.description,
        'pending',
        body.risk_level || 'low',
        body.environment || 'test',
        '00000000-0000-0000-0000-000000000001',
        body.skill_id || null,
        JSON.stringify(body.context || {}),
        id,
      ]
    );

    // Link task to session
    await pool.query(
      `INSERT INTO session_task_links (session_id, task_id, link_type)
       VALUES ($1, $2, $3)
       ON CONFLICT (session_id, task_id) DO NOTHING`,
      [id, taskId, 'direct']
    );

    // Update session updated_at
    await pool.query('UPDATE sessions SET updated_at = NOW() WHERE id = $1', [id]);

    reply.status(201);
    return { success: true, data: taskResult.rows[0] };
  });

  // Get session tasks
  app.get('/:id/tasks', async (request, reply) => {
    const { id } = request.params as { id: string };

    const result = await pool.query(
      `SELECT t.* FROM tasks t
       JOIN session_task_links stl ON t.id = stl.task_id
       WHERE stl.session_id = $1
       ORDER BY t.created_at DESC`,
      [id]
    );

    return { success: true, data: result.rows };
  });
}
