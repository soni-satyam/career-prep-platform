import { useEffect, useState } from 'react'
import { adminApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Navigate } from 'react-router-dom'

export default function Admin() {
  const { isAdmin, loading } = useAuth()
  const [stats, setStats] = useState({ total_users: 0, total_sessions: 0, active_features: 0 })
  const [users, setUsers] = useState<Awaited<ReturnType<typeof adminApi.users>>>([])
  const [features, setFeatures] = useState<Awaited<ReturnType<typeof adminApi.features>>>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const [s, u, f] = await Promise.all([
        adminApi.stats(),
        adminApi.users(),
        adminApi.features(),
      ])
      setStats(s)
      setUsers(u)
      setFeatures(f)
    } catch (e: any) {
      setError(e.message)
    }
  }

  useEffect(() => {
    if (isAdmin) load()
  }, [isAdmin])

  if (loading) return null
  if (!isAdmin) return <Navigate to="/home" replace />

  const toggleFeature = async (key: string, enabled: boolean) => {
    setBusy(true)
    try {
      await adminApi.updateFeature(key, !enabled)
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = async (id: number) => {
    setBusy(true)
    try {
      await adminApi.toggleActive(id)
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const toggleAdmin = async (id: number) => {
    setBusy(true)
    try {
      await adminApi.toggleAdmin(id)
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-semibold mb-1">Admin</h1>
      <p className="text-zinc-400 mb-8">Manage users and feature flags.</p>

      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: 'Users', value: stats.total_users },
          { label: 'Prep Sessions', value: stats.total_sessions },
          { label: 'Active Features', value: stats.active_features },
        ].map((s) => (
          <div key={s.label} className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
            <div className="text-3xl font-semibold">{s.value}</div>
            <div className="text-sm text-zinc-500 mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Features */}
      <section className="mb-10">
        <h2 className="font-medium mb-4">Feature Flags</h2>
        <div className="bg-[#111113] border border-zinc-800 rounded-xl divide-y divide-zinc-800">
          {features.map((f) => (
            <div key={f.key} className="flex items-center justify-between px-5 py-4">
              <div>
                <div className="text-sm font-medium">{f.name}</div>
                <div className="text-xs text-zinc-500">{f.description}</div>
                <div className="text-[11px] text-zinc-600 mt-0.5 font-mono">{f.key}</div>
              </div>
              <button
                disabled={busy}
                onClick={() => toggleFeature(f.key, f.enabled)}
                className={`relative h-6 w-11 rounded-full transition ${
                  f.enabled ? 'bg-emerald-500' : 'bg-zinc-700'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition ${
                    f.enabled ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Users */}
      <section>
        <h2 className="font-medium mb-4">Users</h2>
        <div className="bg-[#111113] border border-zinc-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-zinc-500 text-left">
                <th className="px-5 py-3 font-medium">Email</th>
                <th className="px-5 py-3 font-medium">Name</th>
                <th className="px-5 py-3 font-medium">Provider</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-zinc-800/80">
                  <td className="px-5 py-3">
                    {u.email}
                    {u.is_superuser && (
                      <span className="ml-2 text-[10px] uppercase tracking-wide bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">
                        admin
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-zinc-400">{u.full_name || '—'}</td>
                  <td className="px-5 py-3 text-zinc-400">{u.oauth_provider || 'email'}</td>
                  <td className="px-5 py-3">
                    <span
                      className={`text-xs ${u.is_active ? 'text-emerald-400' : 'text-red-400'}`}
                    >
                      {u.is_active ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  <td className="px-5 py-3 space-x-2">
                    <button
                      disabled={busy}
                      onClick={() => toggleActive(u.id)}
                      className="text-xs text-zinc-400 hover:text-white"
                    >
                      {u.is_active ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => toggleAdmin(u.id)}
                      className="text-xs text-zinc-400 hover:text-white"
                    >
                      {u.is_superuser ? 'Revoke admin' : 'Make admin'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
