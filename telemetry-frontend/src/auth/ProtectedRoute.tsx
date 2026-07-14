import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { getSession } from './session'

interface ProtectedRouteProps {
  children: ReactNode
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const session = getSession()
  if (!session) {
    return <Navigate to="/login" replace />
  }
  return children
}
