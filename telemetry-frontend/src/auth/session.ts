import type { StoredSession } from '../types/auth'

const SESSION_KEY = 'telemetry_session'

export function getSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) {
      return null
    }
    return JSON.parse(raw) as StoredSession
  } catch {
    return null
  }
}

export function setSession(session: StoredSession): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY)
}
