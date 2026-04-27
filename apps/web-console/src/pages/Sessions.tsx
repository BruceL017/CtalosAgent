import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getSessions, createSession } from '../api/client.ts'
import type { Session } from '../api/client.ts'

function Sessions() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      const data = await getSessions()
      setSessions(data.data)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate() {
    if (!newTitle.trim()) return
    setCreating(true)
    try {
      await createSession({ title: newTitle })
      setNewTitle('')
      loadData()
    } catch (err) {
      alert(`Create failed: ${(err as Error).message}`)
    } finally {
      setCreating(false)
    }
  }

  const statusColor: Record<string, string> = {
    active: '#28a745',
    ended: '#6c757d',
  }

  return (
    <div>
      <h2>Sessions</h2>
      <p style={{ color: '#888', marginBottom: 16 }}>Long-running conversation containers linking messages and tasks.</p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        <input
          type="text"
          placeholder="New session title..."
          value={newTitle}
          onChange={e => setNewTitle(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleCreate()}
          style={{ flex: 1, padding: '8px 12px', borderRadius: 4, border: '1px solid #ddd' }}
        />
        <button
          onClick={handleCreate}
          disabled={creating}
          style={{
            background: '#0066cc', color: '#fff', border: 'none',
            padding: '8px 16px', borderRadius: 4, cursor: creating ? 'not-allowed' : 'pointer',
          }}
        >
          {creating ? '...' : 'Create'}
        </button>
      </div>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: '#dc3545' }}>Error: {error}</p>}

      {!loading && sessions.length === 0 && (
        <p style={{ color: '#888' }}>No sessions yet.</p>
      )}

      {sessions.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #eee', textAlign: 'left' }}>
              <th style={{ padding: 12 }}>Title</th>
              <th style={{ padding: 12 }}>Status</th>
              <th style={{ padding: 12 }}>Created</th>
              <th style={{ padding: 12 }}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map(s => (
              <tr key={s.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={{ padding: 12 }}>
                  <Link to={`/sessions/${s.id}`} style={{ color: '#0066cc', textDecoration: 'none' }}>
                    {s.title}
                  </Link>
                </td>
                <td style={{ padding: 12 }}>
                  <span style={{
                    background: statusColor[s.status] || '#888',
                    color: '#fff', padding: '2px 8px', borderRadius: 12,
                    fontSize: 12, fontWeight: 600,
                  }}>
                    {s.status}
                  </span>
                </td>
                <td style={{ padding: 12, color: '#888', fontSize: 13 }}>
                  {new Date(s.created_at).toLocaleString()}
                </td>
                <td style={{ padding: 12, color: '#888', fontSize: 13 }}>
                  {new Date(s.updated_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default Sessions
