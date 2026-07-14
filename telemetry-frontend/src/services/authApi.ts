import { apiClient } from './apiClient'
import type { LoginRequest, LoginResponse } from '../types/auth'

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>('/api/auth/login', payload)
  return response.data
}

export async function logout(sessionId: string): Promise<void> {
  await apiClient.post('/api/auth/logout', { sessionId })
}
