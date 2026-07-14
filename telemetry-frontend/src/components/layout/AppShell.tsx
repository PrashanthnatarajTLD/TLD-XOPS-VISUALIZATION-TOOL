import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { clearSession, getSession } from '../../auth/session'
import { logout } from '../../services/authApi'

const navItems = [
  { to: '/', label: 'Overview' },
  { to: '/telemetry', label: 'Raw Telemetry' },
  { to: '/dtc', label: 'DTC' },
  { to: '/visualize', label: 'Visualize' },
  { to: '/kpi', label: 'KPI Dashboard' },
  { to: '/ai', label: 'AI (Later)' },
]

export function AppShell() {
  const navigate = useNavigate()
  const session = getSession()

  async function onLogout() {
    if (session?.sessionId) {
      try {
        await logout(session.sessionId)
      } catch {
        // Ignore logout API errors and clear local state anyway.
      }
    }
    clearSession()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">LX</div>
          <div>
            <h1>TLD/XOPS Telemetry</h1>
            <p>Telemetry Analysis Platform</p>
          </div>
        </div>

        <nav className="nav-list">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              end={item.to === '/'}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <h2>TLD/XOPS VISUALIZATION TOOL</h2>
            <p>Logged in as: {session?.user.userid ?? 'Unknown'} ({session?.user.role ?? 'User'})</p>
          </div>
          <button className="btn-secondary" onClick={onLogout} type="button">
            Logout
          </button>
        </header>

        <div className="content-body">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
