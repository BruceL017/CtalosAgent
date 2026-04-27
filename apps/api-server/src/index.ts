import Fastify from 'fastify';
import cors from '@fastify/cors';
import { authMiddleware } from './middleware/auth.js';
import { authRoutes } from './routes/auth.js';
import { taskRoutes } from './routes/tasks.js';
import { eventRoutes } from './routes/events.js';
import { skillRoutes } from './routes/skills.js';
import { toolRoutes } from './routes/tools.js';
import { memoryRoutes } from './routes/memories.js';
import { approvalRoutes } from './routes/approvals.js';
import { rollbackRoutes } from './routes/rollbacks.js';
import { replayRoutes } from './routes/replay.js';
import { providerRoutes } from './routes/providers.js';
import { mcpRoutes } from './routes/mcp.js';
import { auditRoutes } from './routes/audit.js';
import { evalRoutes } from './routes/evals.js';
import { subagentRoutes } from './routes/subagents.js';
import { sessionRoutes } from './routes/sessions.js';

const app = Fastify({
  logger: {
    level: 'info',
    transport: {
      target: 'pino-pretty',
      options: { colorize: true },
    },
  },
});

await app.register(cors, {
  origin: true,
  credentials: true,
});

// Public routes
app.get('/health', async () => ({ status: 'ok', service: 'api-server', version: '0.3.0' }));
await app.register(authRoutes, { prefix: '/api/auth' });

// Auth middleware for protected routes
await app.register(async (protectedApp) => {
  protectedApp.addHook('preHandler', authMiddleware as any);

  await protectedApp.register(taskRoutes, { prefix: '/api/tasks' });
  await protectedApp.register(eventRoutes, { prefix: '/api/events' });
  await protectedApp.register(skillRoutes, { prefix: '/api/skills' });
  await protectedApp.register(toolRoutes, { prefix: '/api/tools' });
  await protectedApp.register(memoryRoutes, { prefix: '/api/memories' });
  await protectedApp.register(approvalRoutes, { prefix: '/api/approvals' });
  await protectedApp.register(rollbackRoutes, { prefix: '/api/rollbacks' });
  await protectedApp.register(replayRoutes, { prefix: '/api/replay' });
  await protectedApp.register(providerRoutes, { prefix: '/api/providers' });
  await protectedApp.register(mcpRoutes, { prefix: '/api/mcp' });
  await protectedApp.register(auditRoutes, { prefix: '/api/audit' });
  await protectedApp.register(evalRoutes, { prefix: '/api/evals' });
  await protectedApp.register(subagentRoutes, { prefix: '/api/subagents' });
  await protectedApp.register(sessionRoutes, { prefix: '/api/sessions' });
});

const PORT = parseInt(process.env.PORT || '3001', 10);
const HOST = process.env.HOST || '0.0.0.0';

try {
  await app.listen({ port: PORT, host: HOST });
  console.log(`API Server v0.2 running at http://${HOST}:${PORT}`);
} catch (err) {
  app.log.error(err);
  process.exit(1);
}
