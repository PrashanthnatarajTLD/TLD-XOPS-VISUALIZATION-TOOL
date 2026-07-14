import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { login } from '../services/authApi'
import { getSession, setSession } from '../auth/session'

export function LoginPage() {
  const existing = getSession()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (existing) {
    return <Navigate to="/" replace />
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')

    if (!username.trim() || !password.trim()) {
      setError('Please enter both username and password.')
      return
    }

    try {
      setLoading(true)
      const result = await login({ username: username.trim(), password })
      setSession({
        sessionId: result.sessionId,
        user: result.user,
      })
      navigate('/telemetry', { replace: true })
    } catch {
      setError('Invalid LINKFMS credentials. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="login-head">
          <div className="brand-mark">LX</div>
          <div>
            <h1>TLD/XOPS Telemetry</h1>
            <p>Sign in with your LINKFMS credentials</p>
          </div>
        </div>

        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            placeholder="Enter LINKFMS username"
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            placeholder="Enter password"
          />
        </label>

        {error && <p className="error-text">{error}</p>}

        <button className="btn-primary" type="submit" disabled={loading}>
          {loading ? 'Signing in...' : 'Login'}
        </button>
      </form>
    </section>
  )
}
