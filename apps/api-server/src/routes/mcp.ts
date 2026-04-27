import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { pool } from '../config/db.js';

export async function mcpRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
) {
  app.get('/servers', async (request, reply) => {
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/mcp/servers`);
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Failed to fetch MCP servers' };
    }
  });

  app.get('/servers/db', async (request, reply) => {
    const result = await pool.query('SELECT * FROM mcp_servers ORDER BY created_at DESC');
    return { success: true, data: result.rows };
  });

  app.post('/servers', async (request, reply) => {
    const body = request.body as Record<string, unknown>;
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/mcp/servers/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Failed to register MCP server' };
    }
  });

  app.get('/servers/:name/tools', async (request, reply) => {
    const { name } = request.params as { name: string };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/mcp/servers/${name}/tools`);
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Failed to fetch MCP tools' };
    }
  });

  app.get('/servers/:name/health', async (request, reply) => {
    const { name } = request.params as { name: string };
    try {
      const runtimeUrl = process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${runtimeUrl}/mcp/servers/${name}/health`);
      const data = await response.json();
      return data;
    } catch (err) {
      reply.status(500);
      return { success: false, error: 'Health check failed' };
    }
  });
}
