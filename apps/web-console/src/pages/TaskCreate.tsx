import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createTask, executeTask } from '../api/client.ts'

function TaskCreate() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [riskLevel, setRiskLevel] = useState('low')
  const [environment, setEnvironment] = useState('test')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const presets = [
    { title: 'Generate Weekly Report', description: 'Generate a weekly data analysis report' },
    { title: 'Create Bug Issue', description: 'Found a bug in the login flow, create a GitHub issue' },
    { title: 'Run SQL Query', description: 'Query the top 10 active users from database' },
  ]

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim() || !description.trim()) return

    setSubmitting(true)
    setError('')

    try {
      const task = await createTask({
        title,
        description,
        risk_level: riskLevel,
        environment,
      })

      // Auto-execute the task
      await executeTask(task.id)

      navigate(`/tasks/${task.id}`)
    } catch (err) {
      setError((err as Error).message)
      setSubmitting(false)
    }
  }

  function applyPreset(p: typeof presets[0]) {
    setTitle(p.title)
    setDescription(p.description)
  }

  return (
    <div>
      <h2>Create New Task</h2>

      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 12, color: '#888', fontWeight: 600 }}>Quick Presets:</label>
        <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          {presets.map(p => (
            <button
              key={p.title}
              type="button"
              onClick={() => applyPreset(p)}
              style={{
                padding: '6px 12px',
                border: '1px solid #ddd',
                borderRadius: 4,
                background: '#fff',
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              {p.title}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div style={{ background: '#f8d7da', color: '#721c24', padding: 12, borderRadius: 4, marginBottom: 16 }}>
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ maxWidth: 600 }}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 600 }}>Title</label>
          <input
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Enter task title..."
            required
            style={{
              width: '100%',
              padding: 10,
              border: '1px solid #ddd',
              borderRadius: 4,
              fontSize: 14,
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 600 }}>Description</label>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Describe what the agent should do..."
            required
            rows={4}
            style={{
              width: '100%',
              padding: 10,
              border: '1px solid #ddd',
              borderRadius: 4,
              fontSize: 14,
              resize: 'vertical',
            }}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 600 }}>Risk Level</label>
            <select
              value={riskLevel}
              onChange={e => setRiskLevel(e.target.value)}
              style={{
                width: '100%',
                padding: 10,
                border: '1px solid #ddd',
                borderRadius: 4,
                fontSize: 14,
              }}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 600 }}>Environment</label>
            <select
              value={environment}
              onChange={e => setEnvironment(e.target.value)}
              style={{
                width: '100%',
                padding: 10,
                border: '1px solid #ddd',
                borderRadius: 4,
                fontSize: 14,
              }}
            >
              <option value="test">Test</option>
              <option value="production">Production</option>
            </select>
          </div>
        </div>

        <button
          type="submit"
          disabled={submitting}
          style={{
            background: submitting ? '#888' : '#0066cc',
            color: '#fff',
            padding: '12px 24px',
            border: 'none',
            borderRadius: 4,
            fontSize: 14,
            fontWeight: 600,
            cursor: submitting ? 'not-allowed' : 'pointer',
          }}
        >
          {submitting ? 'Creating & Executing...' : 'Create & Execute Task'}
        </button>
      </form>
    </div>
  )
}

export default TaskCreate
