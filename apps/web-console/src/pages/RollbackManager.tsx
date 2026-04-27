import { useEffect, useState } from 'react'
import { getRollbackPlans, executeRollbackPlan, dryRunRollbackPlan, getTasks } from '../api/client.ts'
import type { Task } from '../api/client.ts'

function RollbackManager() {
  const [plans, setPlans] = useState<Record<string, unknown>[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [selectedTask, setSelectedTask] = useState('')
  const [loading, setLoading] = useState(true)
  const [dryRunResult, setDryRunResult] = useState<Record<string, unknown> | null>(null)
  const [dryRunLoading, setDryRunLoading] = useState('')

  useEffect(() => {
    loadTasks()
    loadPlans()
  }, [])

  useEffect(() => {
    loadPlans()
  }, [selectedTask])

  async function loadTasks() {
    try {
      const result = await getTasks(1, 100)
      setTasks(result.data)
    } catch (e) {
      console.error(e)
    }
  }

  async function loadPlans() {
    setLoading(true)
    try {
      const data = await getRollbackPlans(selectedTask || undefined)
      setPlans(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handleExecute(planId: string) {
    if (!confirm('Execute this rollback plan? This action cannot be undone.')) return
    try {
      const result = await executeRollbackPlan(planId)
      alert(result.success ? 'Rollback executed successfully' : `Rollback failed: ${result.error}`)
      loadPlans()
    } catch (e) {
      alert('Rollback execution failed')
    }
  }

  async function handleDryRun(planId: string) {
    setDryRunLoading(planId)
    try {
      const result = await dryRunRollbackPlan(planId)
      setDryRunResult(result)
    } catch (e) {
      alert('Dry-run failed')
    } finally {
      setDryRunLoading('')
    }
  }

  return (
    <div>
      <h2>Rollback Manager</h2>

      <div style={{ marginBottom: 16 }}>
        <label style={{ marginRight: 8 }}>Filter by Task:</label>
        <select value={selectedTask} onChange={e => setSelectedTask(e.target.value)} style={{ padding: 8 }}>
          <option value="">All Tasks</option>
          {tasks.map(t => (
            <option key={t.id} value={t.id}>{t.title}</option>
          ))}
        </select>
      </div>

      {dryRunResult && (dryRunResult.success as boolean) && (
        <div style={{ background: '#e3f2fd', border: '1px solid #90caf9', borderRadius: 8, padding: 16, marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>Dry-Run Preview</h3>
            <button onClick={() => setDryRunResult(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16 }}>&times;</button>
          </div>
          <p style={{ fontSize: 13, marginBottom: 8 }}><strong>{dryRunResult.summary as string}</strong></p>
          <div style={{ fontSize: 12, marginBottom: 8 }}>
            <span style={{ marginRight: 16 }}><strong>Strategy:</strong> {dryRunResult.strategy as string}</span>
            <span style={{ marginRight: 16 }}><strong>Risk:</strong> {dryRunResult.estimated_risk as string}</span>
            <span><strong>Already Executed:</strong> {dryRunResult.already_executed ? 'Yes' : 'No'}</span>
          </div>
          <div style={{ fontSize: 12, marginBottom: 8 }}>
            <strong>Affected Resources:</strong> {(dryRunResult.affected_resources as string[] || []).join(', ') || 'None'}
          </div>
          <div style={{ fontSize: 12 }}>
            <strong>Preview Steps:</strong>
            <ul style={{ margin: '4px 0', paddingLeft: 20 }}>
              {(dryRunResult.preview_steps as any[] || []).map((step, i) => (
                <li key={i}>{step.action}: {step.description} (risk: {step.estimated_risk})</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {loading && <p>Loading...</p>}

      {plans.length === 0 && !loading && (
        <p style={{ color: '#888' }}>No rollback plans found.</p>
      )}

      {plans.map((p: any) => (
        <div key={p.id} style={{ padding: 16, border: '1px solid #eee', borderRadius: 8, marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div>
              <strong>Strategy: {p.strategy}</strong>
              <span style={{
                marginLeft: 12,
                padding: '2px 8px',
                borderRadius: 12,
                fontSize: 11,
                background: p.executed ? '#28a745' : '#ffc107',
                color: '#fff',
              }}>
                {p.executed ? 'Executed' : 'Pending'}
              </span>
            </div>
            <span style={{ fontSize: 12, color: '#888' }}>
              {new Date(p.created_at).toLocaleString()}
            </span>
          </div>
          <pre style={{ fontSize: 12, background: '#f4f4f4', padding: 8, borderRadius: 4, marginTop: 8 }}>
            {JSON.stringify(p.plan, null, 2)}
          </pre>
          {!p.executed && (
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button
                onClick={() => handleDryRun(p.id)}
                disabled={dryRunLoading === p.id}
                style={{
                  background: '#0066cc',
                  color: '#fff',
                  border: 'none',
                  padding: '6px 16px',
                  borderRadius: 4,
                  cursor: dryRunLoading === p.id ? 'not-allowed' : 'pointer',
                }}
              >
                {dryRunLoading === p.id ? 'Running...' : 'Dry Run'}
              </button>
              <button
                onClick={() => handleExecute(p.id)}
                style={{
                  background: '#dc3545',
                  color: '#fff',
                  border: 'none',
                  padding: '6px 16px',
                  borderRadius: 4,
                  cursor: 'pointer',
                }}
              >
                Execute Rollback
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default RollbackManager
