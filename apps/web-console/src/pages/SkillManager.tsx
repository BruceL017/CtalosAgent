import { useEffect, useState } from 'react'
import { getSkills, getSkillVersions } from '../api/client.ts'
import type { Skill } from '../api/client.ts'

function SkillManager() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [versions, setVersions] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadSkills()
  }, [])

  async function loadSkills() {
    try {
      const data = await getSkills()
      setSkills(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function viewVersions(skill: Skill) {
    setSelectedSkill(skill)
    try {
      const data = await getSkillVersions(skill.id)
      setVersions(data)
    } catch (e) {
      console.error(e)
    }
  }

  const statusColor: Record<string, string> = {
    active: '#28a745',
    deprecated: '#dc3545',
    draft: '#ffc107',
  }

  return (
    <div>
      <h2>Skill & SOP Manager</h2>

      {loading && <p>Loading...</p>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <div>
          <h3>Skills ({skills.length})</h3>
          {skills.map(s => (
            <div
              key={s.id}
              onClick={() => viewVersions(s)}
              style={{
                padding: 12,
                borderRadius: 4,
                border: selectedSkill?.id === s.id ? '2px solid #0066cc' : '1px solid #eee',
                marginBottom: 8,
                cursor: 'pointer',
                background: '#f8f9fa',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong>{s.name}</strong>
                <span style={{
                  background: statusColor[s.status] || '#888',
                  color: '#fff',
                  padding: '2px 8px',
                  borderRadius: 12,
                  fontSize: 11,
                }}>
                  {s.status}
                </span>
              </div>
              <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
                {s.domain} | v{s.current_version} | {s.risk_level}
              </div>
              <div style={{ fontSize: 13, marginTop: 4 }}>{s.description}</div>
            </div>
          ))}
        </div>

        <div>
          {selectedSkill && (
            <div>
              <h3>Versions: {selectedSkill.name}</h3>
              {versions.map((v: any) => (
                <div key={v.id} style={{ padding: 12, border: '1px solid #eee', borderRadius: 4, marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong>v{v.version}</strong>
                    <span style={{ fontSize: 11, color: '#888' }}>
                      {v.eval_score ? `Score: ${v.eval_score}` : ''}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: '#555', marginTop: 4 }}>{v.changelog}</div>
                  <pre style={{ fontSize: 11, background: '#f4f4f4', padding: 8, borderRadius: 4, marginTop: 8 }}>
                    {JSON.stringify(v.content, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default SkillManager
