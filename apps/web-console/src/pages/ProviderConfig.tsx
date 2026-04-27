import { useEffect, useState } from 'react'
import { getProviders, getProviderHealth, getProviderStats } from '../api/client.ts'
import type { ProviderConfig as ProviderConfigType, ProviderHealth, ProviderStats } from '../api/client.ts'

function ProviderConfig() {
  const [providers, setProviders] = useState<ProviderConfigType[]>([])
  const [defaultProvider, setDefaultProvider] = useState('')
  const [health, setHealth] = useState<ProviderHealth[]>([])
  const [stats, setStats] = useState<ProviderStats[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAll()
  }, [])

  async function loadAll() {
    try {
      const [pData, hData, sData] = await Promise.all([
        getProviders(),
        getProviderHealth().catch(() => ({ data: [] })),
        getProviderStats().catch(() => ({ data: [] })),
      ])
      setDefaultProvider(pData.default_provider)
      setProviders(pData.providers)
      setHealth(hData.data || [])
      setStats(sData.data || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const healthMap = new Map(health.map(h => [h.provider, h]))
  const statsMap = new Map(stats.map(s => [s.provider, s]))

  const totalRequests = stats.reduce((sum, s) => sum + (s.total_requests || 0), 0)
  const totalTokens = stats.reduce((sum, s) => sum + (s.total_tokens || 0), 0)
  const avgLatency = stats.length > 0
    ? Math.round(stats.reduce((sum, s) => sum + (s.avg_latency_ms || 0), 0) / stats.length)
    : 0
  const totalErrors = stats.reduce((sum, s) => sum + (s.errors || 0), 0)

  return (
    <div>
      <h2>Model Provider Configuration</h2>
      <div style={{ marginBottom: 16 }}>
        <strong>Default Provider:</strong>{' '}
        <span style={{ color: '#0066cc', fontWeight: 600 }}>{defaultProvider}</span>
      </div>

      {loading && <p>Loading...</p>}

      {/* Metrics Overview */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
        gap: 12,
        marginBottom: 24,
      }}>
        <MetricCard label="Total Requests" value={totalRequests.toLocaleString()} color="#0066cc" />
        <MetricCard label="Total Tokens" value={totalTokens.toLocaleString()} color="#28a745" />
        <MetricCard label="Avg Latency" value={`${avgLatency}ms`} color="#fd7e14" />
        <MetricCard label="Errors" value={totalErrors.toLocaleString()} color={totalErrors > 0 ? '#dc3545' : '#6c757d'} />
      </div>

      {/* Provider Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
        {providers.map(p => {
          const h = healthMap.get(p.provider)
          const s = statsMap.get(p.provider)
          return (
            <div
              key={p.provider}
              style={{
                padding: 16,
                borderRadius: 8,
                border: p.is_default ? '2px solid #0066cc' : '1px solid #eee',
                background: '#fff',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong style={{ textTransform: 'capitalize', fontSize: 16 }}>{p.name}</strong>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  {p.is_default && (
                    <span style={{
                      background: '#0066cc',
                      color: '#fff',
                      padding: '2px 8px',
                      borderRadius: 12,
                      fontSize: 11,
                    }}>DEFAULT</span>
                  )}
                  {h && (
                    <span style={{
                      background: h.healthy ? '#28a745' : '#dc3545',
                      color: '#fff',
                      padding: '2px 8px',
                      borderRadius: 12,
                      fontSize: 11,
                    }}>
                      {h.healthy ? 'Healthy' : 'Unhealthy'}
                    </span>
                  )}
                </div>
              </div>

              <div style={{ marginTop: 8, fontSize: 14, color: '#555' }}>
                Model: {p.model}
              </div>

              <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <span style={{
                  background: p.is_active ? '#e8f5e9' : '#ffebee',
                  color: p.is_active ? '#2e7d32' : '#c62828',
                  padding: '2px 8px',
                  borderRadius: 12,
                  fontSize: 11,
                  fontWeight: 600,
                }}>
                  {p.is_active ? 'Active' : 'Inactive'}
                </span>
                {h && (
                  <span style={{
                    background: '#f5f5f5',
                    color: '#555',
                    padding: '2px 8px',
                    borderRadius: 12,
                    fontSize: 11,
                  }}>
                    {h.latency_ms}ms
                  </span>
                )}
              </div>

              {s && (
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #f0f0f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#666', marginBottom: 4 }}>
                    <span>Requests</span>
                    <span>{s.total_requests.toLocaleString()}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#666', marginBottom: 4 }}>
                    <span>Tokens</span>
                    <span>{s.total_tokens.toLocaleString()}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#666' }}>
                    <span>Avg Latency</span>
                    <span>{s.avg_latency_ms}ms</span>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div style={{ marginTop: 24, padding: 16, background: '#f8f9fa', borderRadius: 8 }}>
        <h4 style={{ marginTop: 0 }}>Supported Providers</h4>
        <ul style={{ fontSize: 14, color: '#555', lineHeight: 1.8 }}>
          <li><strong>OpenAI</strong> — GPT-4o, GPT-4, GPT-3.5</li>
          <li><strong>Anthropic Claude</strong> — Claude 3.5 Sonnet, Claude 3 Opus</li>
          <li><strong>Google Gemini</strong> — Gemini 1.5 Pro</li>
          <li><strong>DeepSeek</strong> — DeepSeek Chat</li>
          <li><strong>Zhipu (智谱)</strong> — GLM-4</li>
          <li><strong>Moonshot (Kimi)</strong> — Moonshot v1</li>
        </ul>
        <p style={{ fontSize: 13, color: '#888' }}>
          Configure API keys via environment variables (see .env.example).
          Fallback chain: default → next available provider.
        </p>
      </div>
    </div>
  )
}

function MetricCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      padding: 16,
      background: '#fff',
      borderRadius: 8,
      border: '1px solid #eee',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>{label}</div>
    </div>
  )
}

export default ProviderConfig
