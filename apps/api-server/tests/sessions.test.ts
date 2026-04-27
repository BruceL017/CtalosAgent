import { describe, it, expect } from 'vitest'

const API_URL = process.env.API_URL || 'http://127.0.0.1:3001'

describe('Session API', () => {
  it('should create, list, and retrieve a session', async () => {
    const create = await fetch(`${API_URL}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'Test Session', description: 'For testing' }),
    })
    const createJson = await create.json()
    expect(createJson.success).toBe(true)
    expect(createJson.data.title).toBe('Test Session')

    const sessionId = createJson.data.id

    const list = await fetch(`${API_URL}/api/sessions`)
    const listJson = await list.json()
    expect(listJson.success).toBe(true)
    expect(listJson.data.some((s: any) => s.id === sessionId)).toBe(true)

    const get = await fetch(`${API_URL}/api/sessions/${sessionId}`)
    const getJson = await get.json()
    expect(getJson.success).toBe(true)
    expect(getJson.data.id).toBe(sessionId)
    expect(Array.isArray(getJson.data.messages)).toBe(true)
    expect(Array.isArray(getJson.data.tasks)).toBe(true)
  })

  it('should add messages to a session', async () => {
    const create = await fetch(`${API_URL}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'Message Test' }),
    })
    const { data: session } = await create.json()

    const msg = await fetch(`${API_URL}/api/sessions/${session.id}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: 'user', content: 'Hello' }),
    })
    const msgJson = await msg.json()
    expect(msgJson.success).toBe(true)
    expect(msgJson.data.content).toBe('Hello')

    const messages = await fetch(`${API_URL}/api/sessions/${session.id}/messages`)
    const msgsJson = await messages.json()
    expect(msgsJson.data.length).toBeGreaterThanOrEqual(1)
  })

  it('should create task within a session', async () => {
    const create = await fetch(`${API_URL}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'Task Test' }),
    })
    const { data: session } = await create.json()

    const task = await fetch(`${API_URL}/api/sessions/${session.id}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'Session Task', description: 'Test' }),
    })
    const taskJson = await task.json()
    expect(taskJson.success).toBe(true)
    expect(taskJson.data.session_id).toBe(session.id)
  })
})
