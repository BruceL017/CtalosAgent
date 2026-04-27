const API_BASE = '/api'

function getAuthHeaders(): Record<string, string> {
  const saved = localStorage.getItem('agent_auth')
  if (saved) {
    try {
      const { token } = JSON.parse(saved)
      if (token) return { Authorization: `Bearer ${token}` }
    } catch {
      // ignore
    }
  }
  return {}
}

function authHeaders(contentType = false): Record<string, string> {
  const headers = getAuthHeaders()
  if (contentType) {
    headers['Content-Type'] = 'application/json'
  }
  return headers
}

export interface Task {
  id: string
  title: string
  description: string
  status: string
  risk_level: string
  environment: string
  created_at: string
  updated_at: string
  result?: Record<string, unknown>
  error_message?: string
}

export interface TaskEvent {
  id: string
  task_id: string
  event_type: string
  sequence: number
  payload: Record<string, unknown>
  created_at: string
}

export interface Memory {
  id: string
  memory_type: string
  content: string
  scope: string
  confidence: number
  is_active: boolean
  created_at: string
}

export interface Skill {
  id: string
  name: string
  description: string
  domain: string
  current_version: string
  status: string
  risk_level?: string
  updated_at: string
}

export interface Approval {
  id: string
  task_id: string
  action_type: string
  status: string
  reason: string
  created_at: string
}

export interface ProviderConfig {
  provider: string
  name?: string
  model: string
  is_active: boolean
  is_default: boolean
  status: string
  configured?: boolean
}

export interface ProviderHealth {
  provider: string
  healthy: boolean
  latency_ms: number
  last_checked: string
}

export interface ProviderStats {
  provider: string
  total_requests: number
  total_tokens: number
  avg_latency_ms: number
  errors: number
}

export interface MCPServer {
  name: string
  transport: string
  capabilities?: string[]
  permissions?: string[]
  is_active: boolean
  health_status?: string
}

export interface Session {
  id: string
  title: string
  description: string
  status: string
  context: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface SessionMessage {
  id: string
  session_id: string
  role: string
  content: string
  created_at: string
}

export interface CreateTaskData {
  title: string
  description: string
  risk_level?: string
  environment?: string
  skill_id?: string
  context?: Record<string, unknown>
  session_id?: string
}

// Auth
export async function login(email: string, password: string): Promise<{ token: string; user: { id: string; email: string; role: string } }> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function getMe(): Promise<{ id: string; email: string; role: string }> {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

// Tasks
export async function getTasks(page = 1, limit = 20): Promise<{ data: Task[]; pagination: { total: number } }> {
  const res = await fetch(`${API_BASE}/tasks?page=${page}&limit=${limit}`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return { data: json.data, pagination: json.pagination }
}

export async function getTask(id: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/tasks/${id}`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function createTask(data: CreateTaskData): Promise<Task> {
  const res = await fetch(`${API_BASE}/tasks`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify(data),
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function executeTask(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/tasks/${id}/execute`, { method: 'POST', headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function cancelTask(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/tasks/${id}/cancel`, { method: 'POST', headers: authHeaders() })
  return res.json()
}

export async function pauseTask(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/tasks/${id}/pause`, { method: 'POST', headers: authHeaders() })
  return res.json()
}

export async function resumeTask(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/tasks/${id}/resume`, { method: 'POST', headers: authHeaders() })
  return res.json()
}

export async function rollbackTask(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/tasks/${id}/rollback`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({}),
  })
  return res.json()
}

export async function getTaskEvents(id: string): Promise<TaskEvent[]> {
  const res = await fetch(`${API_BASE}/tasks/${id}/events`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function getTaskToolCalls(id: string): Promise<Record<string, unknown>[]> {
  const res = await fetch(`${API_BASE}/tasks/${id}/tool-calls`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

// Skills
export async function getSkills(): Promise<Skill[]> {
  const res = await fetch(`${API_BASE}/skills`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function getSkillVersions(id: string): Promise<Record<string, unknown>[]> {
  const res = await fetch(`${API_BASE}/skills/${id}/versions`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

// Memories
export async function getMemories(params?: { type?: string; scope?: string; search?: string }): Promise<{ data: Memory[]; pagination: { total: number } }> {
  const qs = new URLSearchParams()
  if (params?.type) qs.set('type', params.type)
  if (params?.scope) qs.set('scope', params.scope)
  if (params?.search) qs.set('search', params.search)
  const res = await fetch(`${API_BASE}/memories?${qs}`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return { data: json.data, pagination: json.pagination }
}

export async function deactivateMemory(id: string): Promise<void> {
  await fetch(`${API_BASE}/memories/${id}/deactivate`, { method: 'PATCH', headers: authHeaders() })
}

// Approvals
export async function getApprovals(status?: string): Promise<Approval[]> {
  const qs = status ? `?status=${status}` : ''
  const res = await fetch(`${API_BASE}/approvals${qs}`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function approveApproval(id: string, reason?: string): Promise<void> {
  await fetch(`${API_BASE}/approvals/${id}/approve`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({ reason }),
  })
}

export async function rejectApproval(id: string, reason?: string): Promise<void> {
  await fetch(`${API_BASE}/approvals/${id}/reject`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({ reason }),
  })
}

// Rollbacks
export async function getRollbackPlans(taskId?: string): Promise<Record<string, unknown>[]> {
  const qs = taskId ? `?task_id=${taskId}` : ''
  const res = await fetch(`${API_BASE}/rollbacks${qs}`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function executeRollbackPlan(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/rollbacks/${id}/execute`, { method: 'POST', headers: authHeaders() })
  return res.json()
}

// Providers
export async function getProviders(): Promise<{ default_provider: string; providers: ProviderConfig[] }> {
  const res = await fetch(`${API_BASE}/providers`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function getProviderHealth(): Promise<{ data: ProviderHealth[] }> {
  const res = await fetch(`${API_BASE}/providers/health`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data || json
}

export async function getProviderStats(): Promise<{ data: ProviderStats[] }> {
  const res = await fetch(`${API_BASE}/providers/stats`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data || json
}

// MCP
export async function getMCPServers(): Promise<MCPServer[]> {
  const res = await fetch(`${API_BASE}/mcp/servers`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

// Audit
export async function getAuditLogs(params?: Record<string, string>): Promise<Record<string, unknown>[]> {
  const qs = new URLSearchParams()
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value) qs.set(key, value)
    })
  }
  const res = await fetch(`${API_BASE}/audit?${qs}`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function dryRunRollbackPlan(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/rollbacks/${id}/dry-run`, { method: 'POST', headers: authHeaders() })
  return res.json()
}

export async function getTaskEval(taskId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/evals/tasks/${taskId}`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function getSubagents(taskId?: string): Promise<Record<string, unknown>[]> {
  const qs = taskId ? `?task_id=${taskId}` : ''
  const res = await fetch(`${API_BASE}/subagents${qs}`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

// Sessions
export async function getSessions(): Promise<{ data: Session[]; pagination: { total: number } }> {
  const res = await fetch(`${API_BASE}/sessions`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return { data: json.data, pagination: json.pagination }
}

export async function getSession(id: string): Promise<Session & { messages: SessionMessage[]; tasks: Task[] }> {
  const res = await fetch(`${API_BASE}/sessions/${id}`, { headers: authHeaders() })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function createSession(data: { title: string; description?: string; context?: Record<string, unknown> }): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify(data),
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function createSessionMessage(sessionId: string, data: { role: string; content: string }): Promise<SessionMessage> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify(data),
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}

export async function createTaskInSession(sessionId: string, data: CreateTaskData): Promise<Task> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/tasks`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify(data),
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.error)
  return json.data
}
