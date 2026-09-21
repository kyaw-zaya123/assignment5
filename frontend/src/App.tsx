import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { LoginPage } from './pages/LoginPage'
import { AdminPage } from './pages/AdminPage'
import { TraderPage } from './pages/TraderPage'
import { DriverPage } from './pages/DriverPage'
import type { ReactNode } from 'react'

function RequireAuth({ roles, children }: { roles?: string[]; children: ReactNode }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) {
    const dest = user.role === 'ADMIN' ? '/admin' : user.role === 'TRADER' ? '/trader' : '/driver'
    return <Navigate to={dest} replace />
  }
  return children
}

function HomeRedirect() {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'ADMIN') return <Navigate to="/admin" replace />
  if (user.role === 'TRADER') return <Navigate to="/trader" replace />
  return <Navigate to="/driver" replace />
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/admin"
          element={
            <RequireAuth roles={['ADMIN']}>
              <AdminPage />
            </RequireAuth>
          }
        />
        <Route
          path="/trader"
          element={
            <RequireAuth roles={['TRADER', 'ADMIN']}>
              <TraderPage />
            </RequireAuth>
          }
        />
        <Route
          path="/driver"
          element={
            <RequireAuth roles={['DRIVER', 'ADMIN']}>
              <DriverPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<HomeRedirect />} />
      </Routes>
    </AuthProvider>
  )
}
