import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import './Navbar.css'

export default function Navbar() {
  const location = useLocation()
  const { user, signOut } = useAuth()

  const initials = user?.user_metadata?.full_name
    ? user.user_metadata.full_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : user?.email?.[0]?.toUpperCase() ?? '?'

  const avatar = user?.user_metadata?.avatar_url

  return (
    <nav className="navbar">
      <Link to="/dashboard" className="navbar-brand">
        <span className="navbar-logo">⚖</span>
        <span className="navbar-title">LexAI</span>
      </Link>

      <div className="navbar-links">
        <Link
          to="/dashboard"
          className={`navbar-link ${location.pathname === '/dashboard' ? 'active' : ''}`}
        >
          Chat
        </Link>
        <Link
          to="/documents"
          className={`navbar-link ${location.pathname === '/documents' ? 'active' : ''}`}
        >
          Documents
        </Link>
      </div>

      {/* User section */}
      <div className="navbar-user">
        <div className="navbar-avatar" title={user?.email}>
          {avatar
            ? <img src={avatar} alt={initials} className="navbar-avatar-img" />
            : <span>{initials}</span>
          }
        </div>
        <button className="navbar-signout" onClick={signOut} title="Sign out">
          Sign out
        </button>
      </div>
    </nav>
  )
}
