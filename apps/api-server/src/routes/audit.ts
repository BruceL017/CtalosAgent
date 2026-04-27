import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function auditRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.get('/logs', async (request, reply) => {
    const { resource_type, resource_id, action, page = '1', limit = '50' } = request.query as Record<string, string>;
    const offset = (parseInt(page) - 1) * parseInt(limit);

    const conditions: string[] = [];
    const params: (string | number)[] = [];
    let paramIdx = 1;

    if (resource_type) {
      conditions.push(`resource_type = $${paramIdx++}`);
      params.push(resource_type);
    }
    if (resource_id) {
      conditions.push(`resource_id = $${paramIdx++}`);
      params.push(resource_id);
    }
    if (action) {
      conditions.push(`action = $${paramIdx++}`);
      params.push(action);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(parseInt(limit), offset);

    const result = await pool.query(
      `SELECT * FROM audit_logs ${whereClause} ORDER BY created_at DESC LIMIT $${paramIdx++} OFFSET $${paramIdx++}`,
      params
    );

    return { success: true, data: result.rows };
  });

  app.get('/trail/:taskId', async (request, reply) => {
    const { taskId } = request.params as { taskId: string };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/tasks/${taskId}/audit-trail`);
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Failed to export audit trail' };
    }
  });

  // GET /api/audit — Query audit logs with filters
  app.get('/', async (request, reply) => {
    const {
      task_id,
      tool_name,
      risk_level,
      environment,
      status,
      event_type,
      from_date,
      to_date,
      page = '1',
      limit = '20',
    } = request.query as Record<string, string>;

    const offset = (parseInt(page) - 1) * parseInt(limit);
    const conditions: string[] = [];
    const params: (string | number)[] = [];
    let paramIdx = 1;

    if (task_id) {
      conditions.push(`te.task_id = $${paramIdx++}`);
      params.push(task_id);
    }
    if (tool_name) {
      conditions.push(`tc.tool_name = $${paramIdx++}`);
      params.push(tool_name);
    }
    if (risk_level) {
      conditions.push(`COALESCE(tc.risk_level, t.risk_level) = $${paramIdx++}`);
      params.push(risk_level);
    }
    if (environment) {
      conditions.push(`COALESCE(tc.environment, t.environment) = $${paramIdx++}`);
      params.push(environment);
    }
    if (status) {
      conditions.push(`COALESCE(tc.status, t.status) = $${paramIdx++}`);
      params.push(status);
    }
    if (event_type) {
      conditions.push(`te.event_type = $${paramIdx++}`);
      params.push(event_type);
    }
    if (from_date) {
      conditions.push(`te.created_at >= $${paramIdx++}`);
      params.push(from_date);
    }
    if (to_date) {
      conditions.push(`te.created_at <= $${paramIdx++}`);
      params.push(to_date);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    const countResult = await pool.query(
      `SELECT COUNT(*) FROM task_events te
       LEFT JOIN tasks t ON te.task_id = t.id
       LEFT JOIN tool_calls tc ON tc.task_id = te.task_id AND tc.created_at <= te.created_at
       ${whereClause}`,
      params
    );

    const total = parseInt(countResult.rows[0].count, 10);

    params.push(parseInt(limit), offset);

    const result = await pool.query(
      `SELECT
         te.id,
         te.task_id,
         te.event_type,
         te.sequence,
         te.payload,
         te.created_at AS event_created_at,
         t.title AS task_title,
         t.status AS task_status,
         t.risk_level AS task_risk_level,
         t.environment AS task_environment,
         tc.tool_name,
         tc.risk_level AS tool_risk_level,
         tc.environment AS tool_environment,
         tc.status AS tool_status
       FROM task_events te
       LEFT JOIN tasks t ON te.task_id = t.id
       LEFT JOIN tool_calls tc ON tc.task_id = te.task_id AND tc.created_at <= te.created_at
       ${whereClause}
       ORDER BY te.created_at DESC
       LIMIT $${paramIdx++} OFFSET $${paramIdx++}`,
      params
    );

    return {
      success: true,
      data: result.rows,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
      },
    };
  });

  // GET /api/audit/export — Export audit data
  app.get('/export', async (request, reply) => {
    const {
      task_id,
      tool_name,
      risk_level,
      environment,
      status,
      event_type,
      from_date,
      to_date,
      format = 'json',
    } = request.query as Record<string, string>;

    const conditions: string[] = [];
    const params: (string | number)[] = [];
    let paramIdx = 1;

    if (task_id) {
      conditions.push(`te.task_id = $${paramIdx++}`);
      params.push(task_id);
    }
    if (tool_name) {
      conditions.push(`tc.tool_name = $${paramIdx++}`);
      params.push(tool_name);
    }
    if (risk_level) {
      conditions.push(`COALESCE(tc.risk_level, t.risk_level) = $${paramIdx++}`);
      params.push(risk_level);
    }
    if (environment) {
      conditions.push(`COALESCE(tc.environment, t.environment) = $${paramIdx++}`);
      params.push(environment);
    }
    if (status) {
      conditions.push(`COALESCE(tc.status, t.status) = $${paramIdx++}`);
      params.push(status);
    }
    if (event_type) {
      conditions.push(`te.event_type = $${paramIdx++}`);
      params.push(event_type);
    }
    if (from_date) {
      conditions.push(`te.created_at >= $${paramIdx++}`);
      params.push(from_date);
    }
    if (to_date) {
      conditions.push(`te.created_at <= $${paramIdx++}`);
      params.push(to_date);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    const result = await pool.query(
      `SELECT
         te.task_id,
         te.event_type,
         tc.tool_name,
         COALESCE(tc.risk_level, t.risk_level) AS risk_level,
         COALESCE(tc.environment, t.environment) AS environment,
         COALESCE(tc.status, t.status) AS status,
         te.created_at,
         te.payload
       FROM task_events te
       LEFT JOIN tasks t ON te.task_id = t.id
       LEFT JOIN tool_calls tc ON tc.task_id = te.task_id AND tc.created_at <= te.created_at
       ${whereClause}
       ORDER BY te.created_at DESC`,
      params
    );

    if (format === 'csv') {
      const headers = ['task_id', 'event_type', 'tool_name', 'risk_level', 'environment', 'status', 'created_at', 'payload'];
      const rows = result.rows.map((row) => [
        row.task_id ?? '',
        row.event_type ?? '',
        row.tool_name ?? '',
        row.risk_level ?? '',
        row.environment ?? '',
        row.status ?? '',
        row.created_at ? new Date(row.created_at).toISOString() : '',
        row.payload ? JSON.stringify(row.payload) : '',
      ]);

      const csv = [headers.join(','), ...rows.map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))].join('\n');

      reply.header('Content-Type', 'text/csv');
      reply.header('Content-Disposition', 'attachment; filename="audit_export.csv"');
      return csv;
    }

    return {
      success: true,
      data: result.rows,
      exported_at: new Date().toISOString(),
    };
  });

  // GET /api/audit/tasks/:id/summary — Task audit summary
  app.get('/tasks/:id/summary', async (request, reply) => {
    const { id } = request.params as { id: string };

    const taskResult = await pool.query('SELECT * FROM tasks WHERE id = $1', [id]);
    if (taskResult.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Task not found' };
    }

    const task = taskResult.rows[0];

    const eventsResult = await pool.query(
      'SELECT COUNT(*) AS total_events FROM task_events WHERE task_id = $1',
      [id]
    );

    const toolCallsResult = await pool.query(
      'SELECT COUNT(*) AS tool_calls_count FROM tool_calls WHERE task_id = $1',
      [id]
    );

    const approvalsResult = await pool.query(
      "SELECT COUNT(*) AS approval_count FROM approvals WHERE task_id = $1 AND status = 'approved'",
      [id]
    );

    const startedAt = task.started_at ? new Date(task.started_at).getTime() : null;
    const completedAt = task.completed_at ? new Date(task.completed_at).getTime() : null;
    const durationMs = completedAt && startedAt
      ? completedAt - startedAt
      : startedAt
        ? Date.now() - startedAt
        : null;

    return {
      success: true,
      data: {
        task_id: id,
        total_events: parseInt(eventsResult.rows[0].total_events, 10),
        tool_calls_count: parseInt(toolCallsResult.rows[0].tool_calls_count, 10),
        approval_count: parseInt(approvalsResult.rows[0].approval_count, 10),
        duration_ms: durationMs,
        risk_level: task.risk_level || null,
      },
    };
  });
}
