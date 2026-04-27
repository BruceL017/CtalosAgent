import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getSession, createSessionMessage, createTaskInSession, executeTask } from '../api/client.ts'
import type { Session, SessionMessage, Task } from '../api/client.ts'

function SessionDetail() {
  const { id } = useParams<{ id: string }>()
  const [session, setSession] = useState<Session | null>(null)
  const [messages, setMessages] = useState<SessionMessage[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [newMessage, setNewMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [creatingTask, setCreatingTask] = useState(false)

  useEffect(() => {
    if (id) loadData()
  }, [id])

  async function loadData() {
    if (!id) return
    try {
      const data = await getSession(id)
      setSession(data)
      setMessages(data.messages || [])
      setTasks(data.tasks || [])
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSendMessage() {
    if (!id || !newMessage.trim()) return
    setSending(true)
    try {
      await createSessionMessage(id, { role: 'user', content: newMessage })
      setNewMessage('')
      loadData()
    } catch (err) {
      alert(`Send failed: ${(err as Error).message}`)
    } finally {
      setSending(false)
    }
  }

  async function handleCreateTask() {
    if (!id || !newTaskTitle.trim()) return
    setCreatingTask(true)
    try {
      const task = await createTaskInSession(id, {
        title: newTaskTitle,
        description: newTaskTitle,
        environment: 'test',
      })
      setNewTaskTitle('')
      await executeTask(task.id)
      loadData()
    } catch (err) {
      alert(`Task creation failed: ${(err as Error).message}`)
    } finally {
      setCreatingTask(false)
    }
  }

  if (loading) return <p>Loading session...</p>
  if (error) return <p style={{ color: '#dc3545' }}>Error: {error}</p>
  if (!session) return <p>Session not found</p>

  return (
    <div>
      <h2>{session.title}</h2>
      <p style={{ color: '#888' }}>{session.description || 'No description'}</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginTop: 24 }}>
        {/* Messages */}
        <div>
          <h3 style={{ marginBottom: 12 }}>Messages ({messages.length})</h3>
          <div style={{
            background: '#f8f9fa', borderRadius: 8, padding: 16,
            maxHeight: 400, overflow: 'auto', marginBottom: 12,
          }}>
            {messages.length === 0 && <p style={{ color: '#888' }}>No messages yet.</p>}
            {messages.map(m => (
              <div key={m.id} style={{
                marginBottom: 12,
                textAlign: m.role === 'user' ? 'right' : 'left',
              }}>
                <div style={{
                  display: 'inline-block',
                  background: m.role === 'user' ? '#0066cc' : '#fff',
                  color: m.role === 'user' ? '#fff' : '#333',
                  padding: '8px 12px', borderRadius: 8,
                  border: m.role === 'user' ? 'none' : '1px solid #ddd',
                  maxWidth: '80%',
                  fontSize: 13,
                }}>
                  {m.content}
                </div>
                <div style={{ fontSize: 10, color: '#888', marginTop: 4 }}>
                  {m.role} · {new Date(m.created_at).toLocaleTimeString()}
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type="text"
              placeholder="Type a message..."
              value={newMessage}
              onChange={e => setNewMessage(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
              style={{ flex: 1, padding: '8px 12px', borderRadius: 4, border: '1px solid #ddd' }}
            />
            <button
              onClick={handleSendMessage}
              disabled={sending}
              style={{
                background: '#28a745', color: '#fff', border: 'none',
                padding: '8px 16px', borderRadius: 4, cursor: sending ? 'not-allowed' : 'pointer',
              }}
            >
              {sending ? '...' : 'Send'}
            </button>
          </div>
        </div>

        {/* Tasks */}
        <div>
          <h3 style={{ marginBottom: 12 }}>Tasks ({tasks.length})</h3>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <input
              type="text"
              placeholder="New task title..."
              value={newTaskTitle}
              onChange={e => setNewTaskTitle(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreateTask()}
              style={{ flex: 1, padding: '8px 12px', borderRadius: 4, border: '1px solid #ddd' }}
            />
            <button
              onClick={handleCreateTask}
              disabled={creatingTask}
              style={{
                background: '#0066cc', color: '#fff', border: 'none',
                padding: '8px 16px', borderRadius: 4, cursor: creatingTask ? 'not-allowed' : 'pointer',
              }}
            >
              {creatingTask ? '...' : 'Create & Run'}
            </button>
          </div>
          {tasks.length === 0 && <p style={{ color: '#888' }}>No tasks in this session.</p>}
          {tasks.map(t => (
            <div key={t.id} style={{
              padding: 12, borderRadius: 4, marginBottom: 8,
              background: '#f8f9fa', border: '1px solid #eee',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Link to={`/tasks/${t.id}`} style={{ color: '#0066cc', textDecoration: 'none', fontWeight: 600 }}>
                  {t.title}
                </Link>
                <span style={{
                  background: t.status === 'completed' ? '#28a745' : t.status === 'failed' ? '#dc3545' : '#0066cc',
                  color: '#fff', padding: '2px 8px', borderRadius: 12, fontSize: 11,
                }}>
                  {t.status}
                </span>
              </div>
              <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
                {t.environment} · {t.risk_level} · {new Date(t.created_at).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default SessionDetail
