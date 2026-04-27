import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getTask, getTaskEvents } from '../api/client.ts'
import type { Task, TaskEvent } from '../api/client.ts'

function TaskReplay() {
  const { id } = useParams<{ id: string }>()
  const [task, setTask] = useState<Task | null>(null)
  const [events, setEvents] = useState<TaskEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (id) loadData()
  }, [id])

  async function loadData() {
    if (!id) return
    try {
      const [t, e] = await Promise.all([getTask(id), getTaskEvents(id)])
      setTask(t)
      setEvents(e)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  function toggleEvent(eventId: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(eventId)) next.delete(eventId)
      else next.add(eventId)
      return next
    })
  }

  const eventTypeColors: Record<string, string> = {
    'task.created': '#0066cc',
    'tool.called': '#28a745',
    'approval.requested': '#fd7e14',
    'task.completed': '#6f42c1',
    'task.failed': '#dc3545',
  }

  function getEventColor(eventType: string) {
    return eventTypeColors[eventType] || '#888'
  }

  function getDuration() {
    if (!task || events.length === 0) return '—'
    const first = new Date(events[0].created_at).getTime()
    const last = new Date(events[events.length - 1].created_at).getTime()
    const ms = last - first
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  if (loading) return <p>Loading replay...</p>
  if (error) return <p style={{ color: '#dc3545' }}>Error: {error}</p>
  if (!task) return <p>Task not found</p>

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link to={`/tasks/${id}`} style={{ color: '#0066cc', textDecoration: 'none', fontSize: 14 }}>
          ← Back to Task Detail
        </Link>
      </div>

      <h2>Replay Timeline</h2>

      <div style={{ background: '#f8f9fa', padding: 20, borderRadius: 8, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 18 }}>{task.title}</h3>
          <span style={{
            background: task.status === 'completed' ? '#28a745' : task.status === 'failed' ? '#dc3545' : '#0066cc',
            color: '#fff', padding: '4px 12px', borderRadius: 12, fontSize: 12, fontWeight: 600,
          }}>
            {task.status}
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12, fontSize: 13 }}>
          <div><strong>Total Events:</strong> {events.length}</div>
          <div><strong>Duration:</strong> {getDuration()}</div>
          <div><strong>Environment:</strong> {task.environment}</div>
          <div><strong>Risk:</strong> {task.risk_level}</div>
        </div>
      </div>

      <div style={{ position: 'relative', paddingLeft: 24 }}>
        <div style={{
          position: 'absolute', left: 11, top: 0, bottom: 0, width: 2, background: '#e0e0e0',
        }} />
        {events.map((event) => {
          const isExpanded = expanded.has(event.id)
          const color = getEventColor(event.event_type)
          return (
            <div key={event.id} style={{ position: 'relative', marginBottom: 16 }}>
              <div style={{
                position: 'absolute', left: -18, top: 2, width: 12, height: 12, borderRadius: '50%',
                background: color, border: '2px solid #fff', boxShadow: '0 0 0 1px #e0e0e0',
              }} />
              <div style={{
                background: '#fff', border: '1px solid #eee', borderRadius: 6, padding: 12,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{
                      fontSize: 11, fontWeight: 600, color: '#fff', background: color,
                      padding: '2px 8px', borderRadius: 4,
                    }}>
                      {event.event_type}
                    </span>
                    <span style={{ fontSize: 12, color: '#888' }}>
                      #{event.sequence}
                    </span>
                  </div>
                  <span style={{ fontSize: 11, color: '#888' }}>
                    {new Date(event.created_at).toLocaleString()}
                  </span>
                </div>
                <div
                  onClick={() => toggleEvent(event.id)}
                  style={{
                    fontSize: 12, color: '#555', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 4,
                  }}
                >
                  <span>{isExpanded ? '▼' : '▶'}</span>
                  <span>{isExpanded ? 'Hide payload' : 'Show payload'}</span>
                </div>
                {isExpanded && (
                  <pre style={{
                    margin: '8px 0 0 0', background: '#f8f9fa', padding: 12, borderRadius: 4,
                    fontSize: 12, overflow: 'auto', maxHeight: 300, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  }}>
                    {JSON.stringify(event.payload, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          )
        })}
        {events.length === 0 && (
          <p style={{ color: '#888', marginLeft: 8 }}>No events recorded for this task.</p>
        )}
      </div>
    </div>
  )
}

export default TaskReplay
