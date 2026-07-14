export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  sessionId: string
  user: {
    userid: string
    role: string
  }
}

export interface StoredSession {
  sessionId: string
  user: {
    userid: string
    role: string
  }
}
