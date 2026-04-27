import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getTasks, getSkills } from '../api/client.ts'
import type { Task, Skill } from '../api/client.ts'

function Dashboard() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    loadData()
    const interval = setInterval(() => loadData(), 5000)
    return () => clearInterval(interval)
  }, [])

  async function loadData() {
    try {
      const [tasksData, skillsData] = await Promise.all([getTasks(), getSkills()])
      setTasks(tasksData.data)
      setSkills(skillsData)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const statusColor: Record<string, string> = {
    pending: '#888',
    running: '#0066cc',
    completed: '#28a745',
    failed: '#dc3545',
    cancelled: '#6c757d',
  }

  return (
    <div>
      <h2>Dashboard</h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
        <StatCard title="Total Tasks" value={tasks.length} />
        <StatCard title="Running" value={tasks.filter(t => t.status === 'running').length} />
        <StatCard title="Completed" value={tasks.filter(t => t.status === 'completed').length} />
        <StatCard title="Failed" value={tasks.filter(t => t.status === 'failed').length} />
        <StatCard title="Skills" value={skills.length} />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0 }}>Recent Tasks</h3>
        <Link
          to="/tasks/new"
          style={{
            background: '#0066cc',
            color: '#fff',
            padding: '8px 16px',
            borderRadius: 4,
            textDecoration: 'none',
          }}
        >
          + New Task
        </Link>
      </div>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: '#dc3545' }}>Error: {error}</p>}

      {!loading && tasks.length === 0 && (
        <p style={{ color: '#888' }}>No tasks yet. Create your first task!</p>
      )}

      {tasks.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #eee', textAlign: 'left' }}>
              <th style={{ padding: 12 }}>Title</th>
              <th style={{ padding: 12 }}>Status</th>
              <th style={{ padding: 12 }}>Risk</th>
              <th style={{ padding: 12 }}>Environment</th>
              <th style={{ padding: 12 }}>Created</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map(task => (
              <tr key={task.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={{ padding: 12 }}>
                  <Link to={`/tasks/${task.id}`} style={{ color: '#0066cc', textDecoration: 'none' }}>
                    {task.title}
                  </Link>
                </td>
                <td style={{ padding: 12 }}>
                  <span
                    style={{
                      background: statusColor[task.status] || '#888',
                      color: '#fff',
                      padding: '2px 8px',
                      borderRadius: 12,
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    {task.status}
                  </span>
                </td>
                <td style={{ padding: 12 }}>{task.risk_level}</td>
                <td style={{ padding: 12 }}>{task.environment}</td>
                <td style={{ padding: 12, color: '#888', fontSize: 13 }}>
                  {new Date(task.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function StatCard({ title, value }: { title: string; value: number }) {
  return (
    <div style={{ background: '#f8f9fa', padding: 16, borderRadius: 8, border: '1px solid #eee' }}>
      <div style={{ fontSize: 12, color: '#888', textTransform: 'uppercase', letterSpacing: 1 }}>{title}</div>
      <div style={{ fontSize: 32, fontWeight: 700, marginTop: 8 }}>{value}</div>
    </div>
  )
}

export default Dashboard
