import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { login as apiLogin, type AuthUser } from '../api/client'

type AuthState = {
  user: AuthUser | null
  login: (username: string, password: string) => Promise<AuthUser>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

function loadUser(): AuthUser | null {
  const raw = localStorage.getItem('ml_auth')
  if (!raw) return null
  try {
    const user = JSON.parse(raw) as AuthUser
    // Keep Bearer token in sync (PATCH /gates needs it; GET /gates does not)
    if (user?.access_token && !localStorage.getItem('ml_token')) {
      localStorage.setItem('ml_token', user.access_token)
    }
    if (!user?.access_token && !localStorage.getItem('ml_token')) {
      return null
    }
    return user
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => loadUser())

  const value = useMemo<AuthState>(
    () => ({
      user,
      async login(username, password) {
        const data = await apiLogin(username, password)
        localStorage.setItem('ml_token', data.access_token)
        localStorage.setItem('ml_auth', JSON.stringify(data))
        setUser(data)
        return data
      },
      logout() {
        localStorage.removeItem('ml_token')
        localStorage.removeItem('ml_auth')
        setUser(null)
      },
    }),
    [user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside provider')
  return ctx
}
