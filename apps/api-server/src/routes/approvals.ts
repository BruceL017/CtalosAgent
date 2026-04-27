import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';
import { v4 as uuidv4 } from 'uuid';

export async function approvalRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.get('/', async (request, reply) => {
    const { status, task_id, page = '1', limit = '20' } = request.query as Record<string, string>;
    const offset = (parseInt(page) - 1) * parseInt(limit);

    const conditions: string[] = [];
    const params: (string | number)[] = [];
    let paramIdx = 1;

    if (status) {
      conditions.push(`status = $${paramIdx++}`);
      params.push(status);
    }
    if (task_id) {
      conditions.push(`task_id = $${paramIdx++}`);
      params.push(task_id);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    params.push(parseInt(limit), offset);

    const result = await pool.query(
      `SELECT * FROM approvals ${whereClause} ORDER BY created_at DESC LIMIT $${paramIdx++} OFFSET $${paramIdx++}`,
      params
    );

    return { success: true, data: result.rows };
  });

  app.get('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query('SELECT * FROM approvals WHERE id = $1', [id]);
    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Approval not found' };
    }
    return { success: true, data: result.rows[0] };
  });

  app.post('/:id/approve', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as { approver?: string; reason?: string };

    const SYSTEM_ADMIN_ID = '00000000-0000-0000-0000-000000000001';
    const result = await pool.query(
      `UPDATE approvals SET status = 'approved', approver = $1, reason = $2, resolved_at = NOW() WHERE id = $3 RETURNING *`,
      [body.approver || SYSTEM_ADMIN_ID, body.reason || 'Approved', id]
    );

    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Approval not found' };
    }

    // Update task status if this was blocking
    const approval = result.rows[0];
    await pool.query(
      "UPDATE tasks SET status = 'approved', updated_at = NOW() WHERE id = $1",
      [approval.task_id]
    );

    return { success: true, data: result.rows[0] };
  });

  app.post('/:id/reject', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as { approver?: string; reason?: string };

    const SYSTEM_ADMIN_ID = '00000000-0000-0000-0000-000000000001';
    const result = await pool.query(
      `UPDATE approvals SET status = 'rejected', approver = $1, reason = $2, resolved_at = NOW() WHERE id = $3 RETURNING *`,
      [body.approver || SYSTEM_ADMIN_ID, body.reason || 'Rejected', id]
    );

    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Approval not found' };
    }

    const approval = result.rows[0];
    // Update task to failed on rejection
    await pool.query(
      "UPDATE tasks SET status = 'failed', error_message = $1, updated_at = NOW() WHERE id = $2",
      [`Approval rejected: ${body.reason || 'No reason'}`, approval.task_id]
    );

    return { success: true, data: result.rows[0] };
  });

  // PATCH for CLI compatibility
  app.patch('/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const body = request.body as { status: string; reason?: string; approver?: string };

    if (!body.status || !['approved', 'rejected'].includes(body.status)) {
      reply.status(400);
      return { success: false, error: 'Status must be approved or rejected' };
    }

    const SYSTEM_ADMIN_ID = '00000000-0000-0000-0000-000000000001';
    const result = await pool.query(
      `UPDATE approvals SET status = $1, approver = $2, reason = $3, resolved_at = NOW() WHERE id = $4 RETURNING *`,
      [body.status, body.approver || SYSTEM_ADMIN_ID, body.reason || body.status, id]
    );

    if (result.rows.length === 0) {
      reply.status(404);
      return { success: false, error: 'Approval not found' };
    }

    const approval = result.rows[0];

    if (body.status === 'approved') {
      await pool.query(
        "UPDATE tasks SET status = 'approved', updated_at = NOW() WHERE id = $1",
        [approval.task_id]
      );
      // Trigger runtime resume
      try {
        const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
        await fetch(`${runtimeUrl}/tasks/${approval.task_id}/resume`, { method: 'POST' });
      } catch (_e) {
        // Runtime may be down; task stays approved, will resume when available
      }
    } else {
      await pool.query(
        "UPDATE tasks SET status = 'failed', error_message = $1, updated_at = NOW() WHERE id = $2",
        [`Approval rejected: ${body.reason || 'No reason'}`, approval.task_id]
      );
    }

    return { success: true, data: result.rows[0] };
  });
}
