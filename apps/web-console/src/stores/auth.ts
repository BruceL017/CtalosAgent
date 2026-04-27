import { create } from 'zustand'

interface AuthState {
  token: string | null
  user: { id: string; email: string; role: string } | null
  setAuth: (token: string, user: { id: string; email: string; role: string }) => void
  clearAuth: () => void
}

const saved = localStorage.getItem('agent_auth')
let initial: { token: string | null; user: AuthState['user'] } = { token: null, user: null }
if (saved) {
  try {
    initial = JSON.parse(saved)
  } catch {
    // ignore
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  token: initial.token,
  user: initial.user,
  setAuth: (token, user) => {
    localStorage.setItem('agent_auth', JSON.stringify({ token, user }))
    set({ token, user })
  },
  clearAuth: () => {
    localStorage.removeItem('agent_auth')
    set({ token: null, user: null })
  },
}))
