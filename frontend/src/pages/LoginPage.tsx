import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

type Role = 'ADMIN' | 'TRADER' | 'DRIVER'

const ROLES: Array<{
  role: Role
  label: string
  hint: string
  username: string
  password: string
  path: string
}> = [
  {
    role: 'ADMIN',
    label: 'Admin',
    hint: 'Gates · all shipments · command center',
    username: 'admin',
    password: 'Admin123!',
    path: '/admin',
  },
  {
    role: 'TRADER',
    label: 'Trader',
    hint: 'Create cargo · track · AI alerts',
    username: 'trader',
    password: 'Trader123!',
    path: '/trader',
  },
  {
    role: 'DRIVER',
    label: 'Driver',
    hint: 'Trip actions · offline sync',
    username: 'driver1',
    password: 'Driver123!',
    path: '/driver',
  },
]

export function LoginPage() {
  const { user, login, logout } = useAuth()
  const nav = useNavigate()
  const [role, setRole] = useState<Role>('ADMIN')
  const selected = ROLES.find((r) => r.role === role)!
  const [username, setUsername] = useState(selected.username)
  const [password, setPassword] = useState(selected.password)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [switching, setSwitching] = useState(false)

  if (user && !switching) {
    const dest =
      user.role === 'ADMIN' ? '/admin' : user.role === 'TRADER' ? '/trader' : '/driver'
    return (
      <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(ellipse_at_top,_#ecfdf5_0%,_#f1f5f9_50%,_#e2e8f0_100%)] px-4 py-8">
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-lg">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-800">
            Myanmar Logistics Intelligence
          </p>
          <h1 className="mt-1 font-display text-2xl font-bold">Already signed in</h1>
          <p className="mt-2 text-sm text-slate-600">
            {user.username} · <span className="font-semibold">{user.role}</span>
          </p>
          <div className="mt-5 flex flex-col gap-2">
            <button
              type="button"
              className="w-full rounded-lg bg-teal-700 py-2.5 text-sm font-semibold text-white"
              onClick={() => nav(dest)}
            >
              Continue to {user.role === 'ADMIN' ? 'Admin' : user.role === 'TRADER' ? 'Trader' : 'Driver'}
            </button>
            <button
              type="button"
              className="w-full rounded-lg border border-slate-200 py-2.5 text-sm font-semibold text-slate-700"
              onClick={() => {
                logout()
                setSwitching(true)
                setError(null)
              }}
            >
              Switch role / account
            </button>
          </div>
        </div>
      </div>
    )
  }

  function pickRole(next: Role) {
    const r = ROLES.find((x) => x.role === next)!
    setRole(next)
    setUsername(r.username)
    setPassword(r.password)
    setError(null)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const u = await login(username, password)
      if (u.role !== role) {
        logout()
        setSwitching(true)
        setError(`This account is ${u.role}. Select the ${u.role} role, or use the matching demo user.`)
        return
      }
      setSwitching(false)
      nav(selected.path)
    } catch {
      setError('Login failed — check username/password for this role')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(ellipse_at_top,_#ecfdf5_0%,_#f1f5f9_50%,_#e2e8f0_100%)] px-4 py-8">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-lg"
      >
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-800">
          Myanmar Logistics Intelligence
        </p>
        <h1 className="mt-1 font-display text-2xl font-bold">Sign in</h1>
        <p className="mt-1 text-sm text-slate-500">Choose your role first</p>

        <div className="mt-5 grid grid-cols-3 gap-2" role="radiogroup" aria-label="Role">
          {ROLES.map((r) => {
            const active = role === r.role
            return (
              <button
                key={r.role}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => pickRole(r.role)}
                className={
                  active
                    ? 'rounded-xl border-2 border-teal-700 bg-teal-50 px-2 py-3 text-center shadow-sm'
                    : 'rounded-xl border border-slate-200 bg-slate-50 px-2 py-3 text-center hover:border-teal-400'
                }
              >
                <div className={`text-sm font-bold ${active ? 'text-teal-900' : 'text-slate-700'}`}>
                  {r.label}
                </div>
                <div className="mt-1 text-[10px] leading-snug text-slate-500">{r.hint}</div>
              </button>
            )
          })}
        </div>

        <div className="mt-4 rounded-lg border border-dashed border-teal-200 bg-teal-50/60 px-3 py-2 text-xs text-teal-900">
          Signing in as <span className="font-semibold">{selected.label}</span>
          {' · '}
          demo <code className="rounded bg-white px-1">{selected.username}</code>
        </div>

        <label className="mt-4 block text-sm font-medium text-slate-700">
          Username
          <input
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label className="mt-3 block text-sm font-medium text-slate-700">
          Password
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="mt-4 w-full rounded-lg bg-teal-700 py-2.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50"
        >
          {loading ? 'Signing in…' : `Sign in as ${selected.label}`}
        </button>
      </form>
    </div>
  )
}
