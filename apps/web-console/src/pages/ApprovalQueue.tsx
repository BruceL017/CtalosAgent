import { useEffect, useState } from 'react'
import { getApprovals, approveApproval, rejectApproval } from '../api/client.ts'
import type { Approval } from '../api/client.ts'

function ApprovalQueue() {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [filter, setFilter] = useState('pending')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadApprovals()
  }, [filter])

  async function loadApprovals() {
    setLoading(true)
    try {
      const data = await getApprovals(filter)
      setApprovals(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handleApprove(id: string) {
    await approveApproval(id, 'Approved via console')
    loadApprovals()
  }

  async function handleReject(id: string) {
    await rejectApproval(id, 'Rejected via console')
    loadApprovals()
  }

  const statusColor: Record<string, string> = {
    pending: '#ffc107',
    approved: '#28a745',
    rejected: '#dc3545',
  }

  return (
    <div>
      <h2>Approval Queue</h2>
      <div style={{ marginBottom: 16 }}>
        {['pending', 'approved', 'rejected'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            style={{
              padding: '6px 16px',
              marginRight: 8,
              border: filter === s ? '2px solid #0066cc' : '1px solid #ddd',
              background: filter === s ? '#e3f2fd' : '#fff',
              borderRadius: 4,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {loading && <p>Loading...</p>}

      {approvals.length === 0 && !loading && (
        <p style={{ color: '#888' }}>No {filter} approvals.</p>
      )}

      {approvals.map(a => (
        <div key={a.id} style={{ padding: 16, border: '1px solid #eee', borderRadius: 8, marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{
                background: statusColor[a.status] || '#888',
                color: '#fff',
                padding: '2px 8px',
                borderRadius: 12,
                fontSize: 11,
                fontWeight: 600,
              }}>
                {a.status}
              </span>
              <strong style={{ marginLeft: 12 }}>{a.action_type}</strong>
            </div>
            <span style={{ fontSize: 12, color: '#888' }}>
              {new Date(a.created_at).toLocaleString()}
            </span>
          </div>
          <p style={{ margin: '8px 0', fontSize: 14 }}>{a.reason}</p>
          <div style={{ fontSize: 12, color: '#888' }}>Task: {a.task_id}</div>

          {a.status === 'pending' && (
            <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
              <button
                onClick={() => handleApprove(a.id)}
                style={{
                  background: '#28a745',
                  color: '#fff',
                  border: 'none',
                  padding: '6px 16px',
                  borderRadius: 4,
                  cursor: 'pointer',
                }}
              >
                Approve
              </button>
              <button
                onClick={() => handleReject(a.id)}
                style={{
                  background: '#dc3545',
                  color: '#fff',
                  border: 'none',
                  padding: '6px 16px',
                  borderRadius: 4,
                  cursor: 'pointer',
                }}
              >
                Reject
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default ApprovalQueue
