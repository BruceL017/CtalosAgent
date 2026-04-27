import { useEffect, useState } from 'react'
import { getMCPServers } from '../api/client.ts'
import type { MCPServer } from '../api/client.ts'

function MCPServers() {
  const [servers, setServers] = useState<MCPServer[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadServers()
  }, [])

  async function loadServers() {
    try {
      const data = await getMCPServers()
      setServers(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2>MCP Gateway</h2>
      <p style={{ color: '#888', fontSize: 14 }}>
        Model Context Protocol servers for external tool integration.
      </p>

      {loading && <p>Loading...</p>}

      <div style={{ display: 'grid', gap: 16, marginTop: 16 }}>
        {servers.map(s => (
          <div key={s.name} style={{ padding: 16, border: '1px solid #eee', borderRadius: 8, background: '#f8f9fa' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>{s.name}</strong>
              <div style={{ display: 'flex', gap: 8 }}>
                <span style={{
                  background: s.is_active ? '#28a745' : '#dc3545',
                  color: '#fff',
                  padding: '2px 8px',
                  borderRadius: 12,
                  fontSize: 11,
                }}>
                  {s.is_active ? 'Active' : 'Inactive'}
                </span>
                <span style={{
                  background: s.health_status === 'healthy' ? '#28a745' : '#ffc107',
                  color: '#fff',
                  padding: '2px 8px',
                  borderRadius: 12,
                  fontSize: 11,
                }}>
                  {s.health_status}
                </span>
              </div>
            </div>
            <div style={{ fontSize: 13, color: '#555', marginTop: 8 }}>
              Transport: {s.transport}
            </div>
            <div style={{ fontSize: 13, marginTop: 8 }}>
              <strong>Capabilities:</strong>{' '}
              {s.capabilities?.map((c: string) => (
                <span key={c} style={{ background: '#e3f2fd', padding: '2px 6px', borderRadius: 4, marginRight: 4, fontSize: 12 }}>
                  {c}
                </span>
              ))}
            </div>
            <div style={{ fontSize: 13, marginTop: 4 }}>
              <strong>Permissions:</strong>{' '}
              {s.permissions?.map((p: string) => (
                <span key={p} style={{ background: '#fff3e0', padding: '2px 6px', borderRadius: 4, marginRight: 4, fontSize: 12 }}>
                  {p}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {servers.length === 0 && !loading && (
        <div style={{ padding: 24, textAlign: 'center', color: '#888' }}>
          <p>No MCP servers registered.</p>
          <p style={{ fontSize: 13 }}>Register servers via the API or Agent Runtime configuration.</p>
        </div>
      )}
    </div>
  )
}

export default MCPServers
