import { useEffect, useState } from 'react'
import { getMemories, deactivateMemory } from '../api/client.ts'
import type { Memory } from '../api/client.ts'

function MemoryManager() {
  const [memories, setMemories] = useState<Memory[]>([])
  const [filter, setFilter] = useState({ type: '', scope: '', search: '' })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadMemories()
  }, [filter])

  async function loadMemories() {
    setLoading(true)
    try {
      const result = await getMemories(filter)
      setMemories(result.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handleDeactivate(id: string) {
    if (!confirm('Deactivate this memory?')) return
    await deactivateMemory(id)
    loadMemories()
  }

  const typeColors: Record<string, string> = {
    episodic: '#e3f2fd',
    semantic: '#e8f5e9',
    procedural: '#fff3e0',
    performance: '#fce4ec',
  }

  return (
    <div>
      <h2>Memory Manager</h2>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <select value={filter.type} onChange={e => setFilter(f => ({ ...f, type: e.target.value }))} style={{ padding: 8 }}>
          <option value="">All Types</option>
          <option value="episodic">Episodic</option>
          <option value="semantic">Semantic</option>
          <option value="procedural">Procedural</option>
          <option value="performance">Performance</option>
        </select>
        <select value={filter.scope} onChange={e => setFilter(f => ({ ...f, scope: e.target.value }))} style={{ padding: 8 }}>
          <option value="">All Scopes</option>
          <option value="global">Global</option>
          <option value="task">Task</option>
        </select>
        <input
          placeholder="Search memories..."
          value={filter.search}
          onChange={e => setFilter(f => ({ ...f, search: e.target.value }))}
          style={{ padding: 8, flex: 1 }}
        />
      </div>

      {loading && <p>Loading...</p>}

      <div style={{ display: 'grid', gap: 12 }}>
        {memories.map(m => (
          <div
            key={m.id}
            style={{
              padding: 16,
              borderRadius: 8,
              background: typeColors[m.memory_type] || '#f8f9fa',
              border: m.is_active ? '1px solid #ddd' : '1px solid #ccc',
              opacity: m.is_active ? 1 : 0.6,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: '#888' }}>
                  {m.memory_type}
                </span>
                <span style={{ fontSize: 11, color: '#888', marginLeft: 8 }}>
                  scope: {m.scope} | confidence: {m.confidence}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {!m.is_active && <span style={{ fontSize: 11, color: '#dc3545' }}>INACTIVE</span>}
                {m.is_active && (
                  <button
                    onClick={() => handleDeactivate(m.id)}
                    style={{ fontSize: 11, padding: '2px 8px', cursor: 'pointer' }}
                  >
                    Deactivate
                  </button>
                )}
              </div>
            </div>
            <p style={{ margin: '8px 0', fontSize: 14 }}>{m.content}</p>
            <div style={{ fontSize: 11, color: '#888' }}>
              {new Date(m.created_at).toLocaleString()}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default MemoryManager
