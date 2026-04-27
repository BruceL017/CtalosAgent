import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getTask, getTaskEvents, getTaskToolCalls, getTaskEval, cancelTask, pauseTask, resumeTask, rollbackTask } from '../api/client.ts'
import type { Task, TaskEvent } from '../api/client.ts'

function TaskDetail() {
  const { id } = useParams<{ id: string }>()
  const [task, setTask] = useState<Task | null>(null)
  const [events, setEvents] = useState<TaskEvent[]>([])
  const [toolCalls, setToolCalls] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState('')
  const [evalData, setEvalData] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    if (id) {
      loadData()
      loadEval()
    }
    const interval = setInterval(() => {
      if (id) {
        loadData()
        loadEval()
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [id])

  async function loadEval() {
    if (!id) return
    try {
      const data = await getTaskEval(id)
      setEvalData(data)
    } catch (_e) {
      setEvalData(null)
    }
  }

  async function loadData() {
    if (!id) return
    try {
      const [t, e, tc] = await Promise.all([
        getTask(id),
        getTaskEvents(id),
        getTaskToolCalls(id),
      ])
      setTask(t)
      setEvents(e)
      setToolCalls(tc)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function handleAction(action: string, fn: () => Promise<unknown>) {
    setActionLoading(action)
    try {
      await fn()
      loadData()
    } catch (e) {
      alert(`${action} failed: ${e}`)
    } finally {
      setActionLoading('')
    }
  }

  const statusColor: Record<string, string> = {
    pending: '#888', planning: '#6f42c1', running: '#0066cc',
    awaiting_approval: '#ffc107', approved: '#17a2b8',
    paused: '#fd7e14', retrying: '#6f42c1',
    completed: '#28a745', failed: '#dc3545',
    cancelled: '#6c757d', rolling_back: '#e83e8c', rolled_back: '#6c757d',
  }

  if (loading) return <p>Loading task...</p>
  if (error) return <p style={{ color: '#dc3545' }}>Error: {error}</p>
  if (!task) return <p>Task not found</p>

  return (
    <div>
      <h2>Task Detail</h2>

      <div style={{ background: '#f8f9fa', padding: 20, borderRadius: 8, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 20 }}>{task.title}</h3>
          <span style={{
            background: statusColor[task.status] || '#888',
            color: '#fff', padding: '4px 12px', borderRadius: 12,
            fontSize: 12, fontWeight: 600,
          }}>
            {task.status}
          </span>
        </div>
        <p style={{ color: '#555', marginBottom: 16 }}>{task.description}</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, fontSize: 13 }}>
          <div><strong>Risk:</strong> {task.risk_level}</div>
          <div><strong>Environment:</strong> {task.environment}</div>
          <div><strong>Created:</strong> {new Date(task.created_at).toLocaleString()}</div>
          <div><strong>Updated:</strong> {new Date(task.updated_at).toLocaleString()}</div>
        </div>

        <div style={{ marginTop: 12 }}>
          <Link to={`/tasks/${task.id}/replay`} style={{ color: '#0066cc', textDecoration: 'none', fontSize: 14, fontWeight: 600 }}>
            View Replay →
          </Link>
        </div>

        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          {task.status === 'running' && (
            <>
              <ActionButton label="Cancel" loading={actionLoading === 'cancel'} onClick={() => handleAction('cancel', () => cancelTask(task.id))} color="#dc3545" />
              <ActionButton label="Pause" loading={actionLoading === 'pause'} onClick={() => handleAction('pause', () => pauseTask(task.id))} color="#fd7e14" />
            </>
          )}
          {task.status === 'paused' && (
            <ActionButton label="Resume" loading={actionLoading === 'resume'} onClick={() => handleAction('resume', () => resumeTask(task.id))} color="#28a745" />
          )}
          {(task.status === 'completed' || task.status === 'failed') && (
            <ActionButton label="Rollback" loading={actionLoading === 'rollback'} onClick={() => handleAction('rollback', () => rollbackTask(task.id))} color="#6f42c1" />
          )}
        </div>
      </div>

      {evalData && (
        <div style={{ background: '#e8f5e9', border: '1px solid #a5d6a7', borderRadius: 8, padding: 16, marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h4 style={{ margin: 0 }}>Eval Score</h4>
            <span style={{
              fontSize: 24, fontWeight: 700,
              color: (evalData.score as number) >= 0.8 ? '#28a745' : (evalData.score as number) >= 0.6 ? '#fd7e14' : '#dc3545',
            }}>
              {((evalData.score as number) * 100).toFixed(1)}%
            </span>
          </div>
          <div style={{ fontSize: 12, color: '#555', marginBottom: 8 }}>
            {evalData.feedback as string}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8, fontSize: 12 }}>
            {evalData.metrics ? Object.entries(evalData.metrics as Record<string, unknown>).map(([k, v]) => {
              if (typeof v !== 'number') return null
              if (['total_tools', 'success_tools', 'failed_tools', 'total_duration_ms'].includes(k)) return null
              return (
                <div key={k} style={{ background: '#fff', padding: '6px 10px', borderRadius: 4 }}>
                  <div style={{ color: '#888', fontSize: 11, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</div>
                  <div style={{ fontWeight: 600 }}>{(v * 100).toFixed(0)}%</div>
                </div>
              )
            }) : null}
          </div>
        </div>
      )}

      {task.error_message && (
        <div style={{ background: '#f8d7da', color: '#721c24', padding: 12, borderRadius: 4, marginBottom: 24 }}>
          <strong>Error:</strong> {task.error_message}
        </div>
      )}

      {task.result && (
        <div style={{ marginBottom: 24 }}>
          <h4 style={{ marginBottom: 12 }}>Result</h4>
          <pre style={{ background: '#f4f4f4', padding: 16, borderRadius: 4, overflow: 'auto', fontSize: 13 }}>
            {JSON.stringify(task.result, null, 2)}
          </pre>
        </div>
      )}

      <h4 style={{ marginBottom: 12 }}>Event Log ({events.length})</h4>
      <div style={{ marginBottom: 24 }}>
        {events.map(event => (
          <EventRow key={event.id} event={event} />
        ))}
      </div>

      <h4 style={{ marginBottom: 12 }}>Tool Calls ({toolCalls.length})</h4>
      <div>
        {toolCalls.map((tc, i) => (
          <ToolCallRow key={i} toolCall={tc} />
        ))}
      </div>
    </div>
  )
}

function ActionButton({ label, loading, onClick, color }: { label: string; loading: boolean; onClick: () => void; color: string }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      style={{
        background: color,
        color: '#fff',
        border: 'none',
        padding: '8px 16px',
        borderRadius: 4,
        cursor: loading ? 'not-allowed' : 'pointer',
        opacity: loading ? 0.7 : 1,
      }}
    >
      {loading ? '...' : label}
    </button>
  )
}

function EventRow({ event }: { event: TaskEvent }) {
  const eventColors: Record<string, string> = {
    'task.created': '#e3f2fd', 'task.completed': '#e8f5e9', 'task.failed': '#ffebee',
    'task.state_changed': '#f3e5f5', 'tool.called': '#fff3e0', 'tool.result': '#e0f7fa',
    'memory.updated': '#e8f5e9', 'skill.updated': '#fce4ec', 'plan.created': '#fff8e1',
    'approval.requested': '#ffebee', 'approval.resolved': '#e8f5e9',
    'subagent.created': '#e3f2fd', 'subagent.completed': '#e8f5e9',
    'rollback.plan_created': '#fff3e0', 'rollback.executed': '#ffebee',
    'eval.completed': '#e0f7fa', 'sop.extracted': '#f3e5f5',
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 12,
      padding: 10, borderRadius: 4, marginBottom: 6,
      background: eventColors[event.event_type] || '#f8f9fa',
      border: '1px solid #eee',
    }}>
      <div style={{ minWidth: 180, fontSize: 11, fontWeight: 600, color: '#555' }}>
        {event.event_type}
      </div>
      <div style={{ flex: 1, fontSize: 12 }}>
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      </div>
      <div style={{ minWidth: 60, fontSize: 11, color: '#888', textAlign: 'right' }}>
        #{event.sequence}
      </div>
    </div>
  )
}

function ToolCallRow({ toolCall }: { toolCall: Record<string, unknown> }) {
  const status = toolCall.status as string
  const statusColor = status === 'success' ? '#28a745' : status === 'failed' ? '#dc3545' : '#888'

  return (
    <div style={{ padding: 12, borderRadius: 4, marginBottom: 8, background: '#f8f9fa', border: '1px solid #eee' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <strong style={{ fontSize: 14 }}>{toolCall.tool_name as string}</strong>
        <span style={{ color: statusColor, fontSize: 12, fontWeight: 600 }}>{status}</span>
      </div>
      <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>
        Duration: {toolCall.duration_ms as number}ms | Risk: {toolCall.risk_level as string} | Env: {toolCall.environment as string}
      </div>
      <details>
        <summary style={{ fontSize: 12, cursor: 'pointer' }}>Input / Output</summary>
        <div style={{ marginTop: 8 }}>
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#888', marginBottom: 4 }}>INPUT</div>
            <pre style={{ margin: 0, fontSize: 12, background: '#fff', padding: 8, borderRadius: 4 }}>
              {JSON.stringify(toolCall.input, null, 2)}
            </pre>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#888', marginBottom: 4 }}>OUTPUT</div>
            <pre style={{ margin: 0, fontSize: 12, background: '#fff', padding: 8, borderRadius: 4 }}>
              {JSON.stringify(toolCall.output, null, 2)}
            </pre>
          </div>
        </div>
      </details>
    </div>
  )
}

export default TaskDetail
