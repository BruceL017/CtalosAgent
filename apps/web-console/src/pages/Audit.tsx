import { useEffect, useState } from 'react'
import { getAuditLogs } from '../api/client.ts'

interface AuditLog {
  id: string
  task_id: string
  event_type: string
  created_at: string
  risk_level: string
  environment: string
  payload?: Record<string, unknown>
}

function Audit() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [filters, setFilters] = useState({
    task_id: '',
    tool_name: '',
    risk_level: '',
    environment: '',
    status: '',
    from_date: '',
    to_date: '',
  })

  useEffect(() => {
    loadLogs()
  }, [])

  async function loadLogs() {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, string> = {}
      Object.entries(filters).forEach(([key, value]) => {
        if (value.trim()) params[key] = value.trim()
      })
      const data = await getAuditLogs(params)
      setLogs(data as unknown as AuditLog[])
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  function handleFilterChange(key: string, value: string) {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  function handleExport() {
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <h2>Audit Log</h2>

      <div style={{
        background: '#f8f9fa', padding: 16, borderRadius: 8, marginBottom: 24,
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12,
      }}>
        <FilterInput label="Task ID" value={filters.task_id} onChange={v => handleFilterChange('task_id', v)} />
        <FilterInput label="Tool Name" value={filters.tool_name} onChange={v => handleFilterChange('tool_name', v)} />
        <FilterInput label="Risk Level" value={filters.risk_level} onChange={v => handleFilterChange('risk_level', v)} />
        <FilterInput label="Environment" value={filters.environment} onChange={v => handleFilterChange('environment', v)} />
        <FilterInput label="Status" value={filters.status} onChange={v => handleFilterChange('status', v)} />
        <FilterInput label="From Date" value={filters.from_date} onChange={v => handleFilterChange('from_date', v)} type="date" />
        <FilterInput label="To Date" value={filters.to_date} onChange={v => handleFilterChange('to_date', v)} type="date" />
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
          <button
            onClick={loadLogs}
            disabled={loading}
            style={{
              background: '#0066cc', color: '#fff', border: 'none',
              padding: '8px 16px', borderRadius: 4, cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? '...' : 'Query'}
          </button>
          <button
            onClick={handleExport}
            disabled={logs.length === 0}
            style={{
              background: '#28a745', color: '#fff', border: 'none',
              padding: '8px 16px', borderRadius: 4, cursor: logs.length === 0 ? 'not-allowed' : 'pointer',
            }}
          >
            Export JSON
          </button>
        </div>
      </div>

      {error && <p style={{ color: '#dc3545', marginBottom: 16 }}>Error: {error}</p>}

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f8f9fa', borderBottom: '2px solid #dee2e6' }}>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Task ID</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Event Type</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Created At</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Risk Level</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Environment</th>
            </tr>
          </thead>
          <tbody>
            {logs.map(log => (
              <tr key={log.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 12 }}>{log.task_id}</td>
                <td style={{ padding: '10px 12px' }}>{log.event_type}</td>
                <td style={{ padding: '10px 12px', color: '#555' }}>{new Date(log.created_at).toLocaleString()}</td>
                <td style={{ padding: '10px 12px' }}>
                  <span style={{
                    background: log.risk_level === 'high' ? '#dc3545' : log.risk_level === 'medium' ? '#fd7e14' : '#28a745',
                    color: '#fff', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                  }}>
                    {log.risk_level}
                  </span>
                </td>
                <td style={{ padding: '10px 12px', color: '#555' }}>{log.environment}</td>
              </tr>
            ))}
            {logs.length === 0 && !loading && (
              <tr>
                <td colSpan={5} style={{ padding: 20, textAlign: 'center', color: '#888' }}>
                  No audit logs found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FilterInput({ label, value, onChange, type = 'text' }: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
}) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4, color: '#555' }}>{label}</label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          width: '100%', padding: '6px 10px', borderRadius: 4, border: '1px solid #ddd',
          fontSize: 13, boxSizing: 'border-box',
        }}
      />
    </div>
  )
}

export default Audit
