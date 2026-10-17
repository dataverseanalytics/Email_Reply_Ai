import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../App'

export default function AuthPage({ mode }) {
  const { setUser } = useAuth()
  const isRegister = mode === 'register'
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const body = isRegister ? form : { email: form.email, password: form.password }
      setUser(await api.post(isRegister ? '/auth/register' : '/auth/login', body))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <div className="auth-side">
        <div className="brand">Replydesk</div>
        <p className="auth-pitch">
          Your inbox, answered in your words. Replydesk drafts a reply to every email from the
          answers you've already written, and you check each one before it's sent.
        </p>
      </div>
      <form className="auth-card" onSubmit={submit}>
        <h1>{isRegister ? 'Create your account' : 'Log in'}</h1>
        {isRegister && (
          <label>Your name
            <input value={form.name} onChange={set('name')} required autoComplete="name" />
          </label>
        )}
        <label>Email
          <input type="email" value={form.email} onChange={set('email')} required autoComplete="email" />
        </label>
        <label>Password
          <input type="password" value={form.password} onChange={set('password')} required
            minLength={isRegister ? 8 : undefined}
            autoComplete={isRegister ? 'new-password' : 'current-password'} />
        </label>
        {isRegister && <small className="hint">At least 8 characters.</small>}
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>
          {busy ? 'Please wait…' : isRegister ? 'Create account' : 'Log in'}
        </button>
        <p className="switch">
          {isRegister
            ? <>Already have an account? <Link to="/login">Log in</Link></>
            : <>New here? <Link to="/register">Create an account</Link></>}
        </p>
      </form>
    </div>
  )
}
