import { createContext, useContext, useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { api } from './api'
import AuthPage from './pages/AuthPage'
import Inbox from './pages/Inbox'
import Knowledge from './pages/Knowledge'
import Presets from './pages/Presets'
import Settings from './pages/Settings'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

function Shell({ children }) {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const logout = async () => {
    await api.post('/auth/logout')
    setUser(null)
    navigate('/login')
  }
  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">Replydesk</div>
        <nav>
          <NavLink to="/" end>Inbox</NavLink>
          <NavLink to="/knowledge">Answers</NavLink>
          <NavLink to="/prompts">Prompts</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="rail-foot">
          <span className="who" title={user.email}>{user.name}</span>
          <button className="link" onClick={logout}>Log out</button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  )
}

function Protected({ children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return <Shell>{children}</Shell>
}

export default function App() {
  const [user, setUser] = useState(undefined) // undefined = still checking session

  useEffect(() => {
    api.get('/auth/me').then(setUser).catch(() => setUser(null))
  }, [])

  if (user === undefined) return <div className="boot">Loading…</div>

  return (
    <AuthContext.Provider value={{ user, setUser }}>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" /> : <AuthPage mode="login" />} />
        <Route path="/register" element={user ? <Navigate to="/" /> : <AuthPage mode="register" />} />
        <Route path="/" element={<Protected><Inbox /></Protected>} />
        <Route path="/knowledge" element={<Protected><Knowledge /></Protected>} />
        <Route path="/prompts" element={<Protected><Presets /></Protected>} />
        <Route path="/settings" element={<Protected><Settings /></Protected>} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </AuthContext.Provider>
  )
}
