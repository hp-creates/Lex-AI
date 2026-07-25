import { useAuth } from '../hooks/useAuth'
import { Navigate } from 'react-router-dom'

/**
 * Wraps protected routes — redirects to /login if not authenticated.
 * Shows a loading state while session is being fetched.
 */
export default function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="auth-loading">
        <div className="auth-spinner" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return children
}
