#!/usr/bin/env node
import { Command } from 'commander';
import chalk from 'chalk';

const API_BASE = process.env.AGENT_API_URL || 'http://127.0.0.1:3001';

async function apiGet(path: string) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}

async function apiPost(path: string, body?: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : '{}',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}

async function apiPatch(path: string, body?: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}

const program = new Command();
program.name('agent').description('Enterprise Agent CLI').version('0.1.0');

// ===================== SESSION =====================
program
  .command('session:create <title>')
  .description('Create a new session')
  .option('-d, --description <desc>', 'session description')
  .action(async (title, opts) => {
    const data = await apiPost('/api/sessions', { title, description: opts.description || '' });
    console.log(chalk.green('Session created:'), data.data.id);
    console.log(JSON.stringify(data.data, null, 2));
  });

program
  .command('session:list')
  .description('List sessions')
  .option('-l, --limit <n>', 'limit', '20')
  .action(async (opts) => {
    const data = await apiGet(`/api/sessions?limit=${opts.limit}`);
    console.log(chalk.blue(`Sessions (${data.data.length}):`));
    for (const s of data.data) {
      console.log(`  ${s.id.slice(0, 8)} | ${s.status} | ${s.title}`);
    }
  });

program
  .command('session:show <id>')
  .description('Show session details with messages and tasks')
  .action(async (id) => {
    const data = await apiGet(`/api/sessions/${id}`);
    console.log(chalk.blue('Session:'), data.data.title);
    console.log(chalk.gray('Messages:'), data.data.messages?.length || 0);
    console.log(chalk.gray('Tasks:'), data.data.tasks?.length || 0);
    console.log(JSON.stringify(data.data, null, 2));
  });

// ===================== CHAT =====================
program
  .command('chat')
  .description('Start an interactive chat (creates a new session)')
  .option('-s, --session <id>', 'use existing session')
  .action(async (opts) => {
    let sessionId = opts.session;
    if (!sessionId) {
      const data = await apiPost('/api/sessions', { title: 'CLI Chat ' + new Date().toISOString() });
      sessionId = data.data.id;
      console.log(chalk.green('Created session:'), sessionId);
    }
    console.log(chalk.blue('Entering chat mode. Type "exit" to quit.'));
    // Simple non-interactive mode for now - accept single message
    console.log(chalk.yellow('Use: agent chat:message <session_id> "<content>"'));
    console.log('Session ID:', sessionId);
  });

program
  .command('chat:message <sessionId> <content>')
  .description('Send a message to a session')
  .action(async (sessionId, content) => {
    const data = await apiPost(`/api/sessions/${sessionId}/messages`, { role: 'user', content });
    console.log(chalk.green('Message sent:'), data.data.id);
  });

// ===================== TASK =====================
program
  .command('task:create <title>')
  .description('Create a task')
  .option('-d, --description <desc>', 'description')
  .option('-e, --environment <env>', 'environment', 'test')
  .option('-s, --session <id>', 'session id')
  .option('--risk <level>', 'risk level', 'low')
  .action(async (title, opts) => {
    let sessionId = opts.session;
    if (!sessionId) {
      const s = await apiPost('/api/sessions', { title: `Task: ${title}` });
      sessionId = s.data.id;
      console.log(chalk.gray('Auto-created session:'), sessionId);
    }
    const data = await apiPost(`/api/sessions/${sessionId}/tasks`, {
      title,
      description: opts.description || title,
      environment: opts.environment,
      risk_level: opts.risk,
    });
    console.log(chalk.green('Task created:'), data.data.id);
    console.log('Session:', sessionId);
  });

program
  .command('task:run <taskId>')
  .description('Execute a task')
  .action(async (taskId) => {
    const data = await apiPost(`/api/tasks/${taskId}/execute`);
    console.log(chalk.green('Task execution started:'), data.data?.status || data.status);
    console.log(JSON.stringify(data, null, 2));
  });

program
  .command('task:status <taskId>')
  .description('Get task status')
  .action(async (taskId) => {
    const data = await apiGet(`/api/tasks/${taskId}`);
    console.log(chalk.blue('Status:'), data.data.status);
    console.log(JSON.stringify(data.data, null, 2));
  });

program
  .command('task:events <taskId>')
  .description('Get task events')
  .action(async (taskId) => {
    const data = await apiGet(`/api/tasks/${taskId}/events`);
    console.log(chalk.blue(`Events (${data.data.length}):`));
    for (const e of data.data) {
      console.log(`  [${e.sequence}] ${e.event_type} | ${new Date(e.created_at).toISOString()}`);
    }
  });

program
  .command('task:replay <taskId>')
  .description('Replay a task')
  .action(async (taskId) => {
    const data = await apiPost(`/api/replay`, { task_id: taskId, replay_type: 'full' });
    console.log(chalk.green('Replay session:'), data.data.id);
  });

program
  .command('task:retry <taskId>')
  .description('Retry a failed task')
  .action(async (taskId) => {
    const data = await apiPost(`/api/tasks/${taskId}/execute`);
    console.log(chalk.green('Retry started:'), data.data?.status || data.status);
  });

program
  .command('task:cancel <taskId>')
  .description('Cancel a task')
  .action(async (taskId) => {
    const data = await apiPost(`/api/tasks/${taskId}/cancel`);
    console.log(chalk.green('Cancelled:'), data.status || data.data?.status);
  });

// ===================== MEMORY =====================
program
  .command('memory:search <query>')
  .description('Search memories')
  .action(async (query) => {
    const data = await apiGet(`/api/memories?search=${encodeURIComponent(query)}`);
    console.log(chalk.blue(`Memories (${data.data.length}):`));
    for (const m of data.data) {
      console.log(`  ${m.id.slice(0, 8)} | ${m.memory_type} | ${m.scope} | ${m.content.slice(0, 60)}...`);
    }
  });

program
  .command('memory:list')
  .description('List memories')
  .option('-t, --type <type>', 'memory type filter')
  .option('-s, --scope <scope>', 'scope filter')
  .action(async (opts) => {
    let url = '/api/memories';
    const params = new URLSearchParams();
    if (opts.type) params.append('type', opts.type);
    if (opts.scope) params.append('scope', opts.scope);
    if (params.toString()) url += '?' + params.toString();
    const data = await apiGet(url);
    console.log(chalk.blue(`Memories (${data.data.length}):`));
    for (const m of data.data) {
      console.log(`  ${m.id.slice(0, 8)} | ${m.memory_type} | ${m.scope} | ${m.content.slice(0, 60)}...`);
    }
  });

// ===================== SKILL =====================
program
  .command('skill:list')
  .description('List skills')
  .action(async () => {
    const data = await apiGet('/api/skills');
    console.log(chalk.blue(`Skills (${data.data.length}):`));
    for (const s of data.data) {
      console.log(`  ${s.id.slice(0, 8)} | ${s.name} | v${s.current_version} | ${s.domain}`);
    }
  });

program
  .command('skill:rollback <skillId>')
  .description('Rollback skill to previous version')
  .option('-v, --version <ver>', 'target version')
  .action(async (skillId, opts) => {
    const data = await apiPost(`/api/skills/${skillId}/rollback`, { version: opts.version });
    console.log(chalk.green('Rollback result:'), data.success);
    console.log(JSON.stringify(data, null, 2));
  });

// ===================== APPROVALS =====================
program
  .command('approvals:list')
  .description('List pending approvals')
  .action(async () => {
    const data = await apiGet('/api/approvals?status=pending');
    console.log(chalk.blue(`Pending approvals (${data.data.length}):`));
    for (const a of data.data) {
      console.log(`  ${a.id.slice(0, 8)} | ${a.action_type} | ${a.status}`);
    }
  });

program
  .command('approvals:approve <id>')
  .description('Approve an approval request')
  .action(async (id) => {
    const data = await apiPatch(`/api/approvals/${id}`, { status: 'approved' });
    console.log(chalk.green('Approved:'), data.data?.id || id);
  });

program
  .command('approvals:reject <id>')
  .description('Reject an approval request')
  .option('-r, --reason <reason>', 'rejection reason', 'Rejected via CLI')
  .action(async (id, opts) => {
    const data = await apiPatch(`/api/approvals/${id}`, { status: 'rejected', reason: opts.reason });
    console.log(chalk.yellow('Rejected:'), data.data?.id || id);
  });

// ===================== ROLLBACK =====================
program
  .command('rollback:execute <planId>')
  .description('Execute a rollback plan')
  .action(async (planId) => {
    const data = await apiPost(`/api/rollbacks/${planId}/execute`);
    console.log(chalk.green('Rollback executed:'), data.success);
    console.log(JSON.stringify(data, null, 2));
  });

program
  .command('rollback:list')
  .description('List rollback plans')
  .action(async () => {
    const data = await apiGet('/api/rollbacks');
    console.log(chalk.blue(`Rollback plans (${data.data.length}):`));
    for (const r of data.data) {
      console.log(`  ${r.id.slice(0, 8)} | ${r.strategy} | executed=${r.executed}`);
    }
  });

// ===================== HEALTH =====================
program
  .command('health')
  .description('Check API health')
  .action(async () => {
    const data = await apiGet('/health');
    console.log(chalk.green('API Server:'), data.status, data.version);
  });

program.parse();
