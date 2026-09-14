import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { prepApi } from '../lib/api'

export default function ProgressPage() {
  const [sessions, setSessions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    prepApi
      .listSessions()
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false))
  }, [])

  const avg =
    sessions.length > 0
      ? Math.round(sessions.reduce((a, s) => a + (s.progress_pct || 0), 0) / sessions.length)
      : 0

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-2xl font-semibold mb-1">Your Progress</h1>
      <p className="text-zinc-400 mb-8">Track preparation across sessions.</p>

      <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5 mb-6">
        <div className="text-3xl font-semibold">{avg}%</div>
        <div className="text-sm text-zinc-500 mt-1">
          Average completion · {sessions.length} session{sessions.length !== 1 ? 's' : ''}
        </div>
      </div>

      {loading && <p className="text-sm text-zinc-500">Loading…</p>}
      <div className="space-y-2">
        {sessions.map((s) => (
          <Link
            key={s.id}
            to={`/sessions/${s.id}`}
            className="flex items-center justify-between p-4 bg-[#111113] border border-zinc-800 rounded-xl hover:border-zinc-600 transition"
          >
            <div>
              <div className="text-sm font-medium">{s.title || `Session #${s.id}`}</div>
              <div className="text-xs text-zinc-500 capitalize mt-0.5">{s.status}</div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-24 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full"
                  style={{ width: `${Math.min(100, s.progress_pct || 0)}%` }}
                />
              </div>
              <span className="text-xs text-zinc-400 w-8 text-right">
                {Math.round(s.progress_pct || 0)}%
              </span>
            </div>
          </Link>
        ))}
        {!loading && sessions.length === 0 && (
          <p className="text-sm text-zinc-500">
            No sessions yet. <Link to="/resume" className="text-white underline">Create one</Link>.
          </p>
        )}
      </div>
    </div>
  )
}
