import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useAuthStore } from './stores/auth.ts'
import Dashboard from './pages/Dashboard.tsx'
import TaskCreate from './pages/TaskCreate.tsx'
import TaskDetail from './pages/TaskDetail.tsx'
import MemoryManager from './pages/MemoryManager.tsx'
import SkillManager from './pages/SkillManager.tsx'
import ApprovalQueue from './pages/ApprovalQueue.tsx'
import RollbackManager from './pages/RollbackManager.tsx'
import ProviderConfig from './pages/ProviderConfig.tsx'
import MCPServers from './pages/MCPServers.tsx'
import Sessions from './pages/Sessions.tsx'
import SessionDetail from './pages/SessionDetail.tsx'
import TaskReplay from './pages/TaskReplay.tsx'
import Audit from './pages/Audit.tsx'
import Login from './pages/Login.tsx'

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  const location = useLocation()
  const active = location.pathname === to
  return (
    <Link
      to={to}
      style={{
        marginRight: 16,
        textDecoration: 'none',
        color: active ? '#0066cc' : '#555',
        fontWeight: active ? 600 : 400,
        paddingBottom: 4,
        borderBottom: active ? '2px solid #0066cc' : '2px solid transparent',
      }}
    >
      {children}
    </Link>
  )
}

function App() {
  const token = useAuthStore(s => s.token)
  const user = useAuthStore(s => s.user)
  const clearAuth = useAuthStore(s => s.clearAuth)
  const navigate = useNavigate()
  const location = useLocation()
  const isLoggedIn = !!token

  // Redirect to login if not authenticated (except login page)
  useEffect(() => {
    if (!isLoggedIn && location.pathname !== '/login') {
      navigate('/login')
    }
  }, [isLoggedIn, location.pathname, navigate])

  function handleLogout() {
    clearAuth()
    navigate('/login')
  }

  // Show login page without nav
  if (!isLoggedIn) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Login />} />
      </Routes>
    )
  }

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', maxWidth: 1400, margin: '0 auto', padding: 20 }}>
      <header style={{ borderBottom: '1px solid #eee', paddingBottom: 16, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1 style={{ margin: 0, fontSize: 24 }}>Enterprise Agent Console v0.3</h1>
          {user && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13 }}>
              <span style={{ color: '#555' }}>
                {user.email}
                <span style={{
                  marginLeft: 8,
                  background: '#e3f2fd',
                  color: '#0066cc',
                  padding: '2px 8px',
                  borderRadius: 12,
                  fontSize: 11,
                  fontWeight: 600,
                  textTransform: 'uppercase',
                }}>
                  {user.role}
                </span>
              </span>
              <button
                onClick={handleLogout}
                style={{
                  padding: '4px 12px',
                  fontSize: 12,
                  border: '1px solid #ddd',
                  borderRadius: 4,
                  background: '#fff',
                  cursor: 'pointer',
                  color: '#555',
                }}
              >
                Logout
              </button>
            </div>
          )}
        </div>
        <nav style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap' }}>
          <NavLink to="/">Dashboard</NavLink>
          <NavLink to="/sessions">Sessions</NavLink>
          <NavLink to="/tasks/new">New Task</NavLink>
          <NavLink to="/memories">Memories</NavLink>
          <NavLink to="/skills">Skills</NavLink>
          <NavLink to="/approvals">Approvals</NavLink>
          <NavLink to="/rollbacks">Rollbacks</NavLink>
          <NavLink to="/providers">Providers</NavLink>
          <NavLink to="/mcp">MCP</NavLink>
          <NavLink to="/audit">Audit</NavLink>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/tasks/new" element={<TaskCreate />} />
        <Route path="/tasks/:id" element={<TaskDetail />} />
        <Route path="/memories" element={<MemoryManager />} />
        <Route path="/skills" element={<SkillManager />} />
        <Route path="/approvals" element={<ApprovalQueue />} />
        <Route path="/rollbacks" element={<RollbackManager />} />
        <Route path="/providers" element={<ProviderConfig />} />
        <Route path="/mcp" element={<MCPServers />} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/sessions/:id" element={<SessionDetail />} />
        <Route path="/tasks/:id/replay" element={<TaskReplay />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/login" element={<Dashboard />} />
      </Routes>
    </div>
  )
}

export default App
