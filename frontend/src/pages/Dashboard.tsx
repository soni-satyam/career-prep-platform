import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  FileText,
  Search,
  Building2,
  MessageSquare,
  HelpCircle,
} from 'lucide-react'
import { prepApi } from '../lib/api'
import { useAuth } from '../lib/auth'

const modules = [
  { to: '/resume', title: 'Resume', desc: 'Tailor for any job', icon: FileText, color: 'bg-emerald-500/15 text-emerald-400', flag: 'resume_tailor' },
  { to: '/jobs', title: 'Job Search', desc: 'Find real jobs', icon: Search, color: 'bg-blue-500/15 text-blue-400', flag: 'job_search' },
  { to: '/companies', title: 'Company Search', desc: 'Explore companies', icon: Building2, color: 'bg-violet-500/15 text-violet-400', flag: 'company_search' },
  { to: '/interview', title: 'Interview Prep', desc: 'Practice with AI', icon: MessageSquare, color: 'bg-amber-500/15 text-amber-400', flag: 'interview_prep' },
  { to: '/quizzes', title: 'Quizzes', desc: 'Sharpen skills', icon: HelpCircle, color: 'bg-rose-500/15 text-rose-400', flag: 'quizzes' },
]

export default function Dashboard() {
  const { user } = useAuth()
  const [sessions, setSessions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const name = user?.full_name?.split(' ')[0] || 'there'

  useEffect(() => {
    prepApi
      .listSessions()
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false))
  }, [])

  const avgProgress =
    sessions.length > 0
      ? Math.round(sessions.reduce((a, s) => a + (s.progress_pct || 0), 0) / sessions.length)
      : 0

  return (
    <div className="p-8 max-w-6xl">
      <h1 className="text-2xl font-semibold mb-1">Good morning, {name}</h1>
      <p className="text-zinc-400 mb-8">Let&apos;s keep building your career.</p>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-10">
        {modules.map(({ to, title, desc, icon: Icon, color }) => (
          <Link
            key={to}
            to={to}
            className="bg-[#111113] border border-zinc-800 rounded-xl p-4 hover:border-zinc-600 transition group"
          >
            <div className={`h-10 w-10 rounded-lg flex items-center justify-center mb-3 ${color}`}>
              <Icon size={20} strokeWidth={1.75} />
            </div>
            <div className="font-medium text-sm group-hover:text-white">{title}</div>
            <div className="text-xs text-zinc-500 mt-0.5">{desc}</div>
          </Link>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-5">
            <h2 className="font-medium">Your progress</h2>
            <Link to="/progress" className="text-xs text-zinc-400 hover:text-white">
              View all
            </Link>
          </div>
          <div className="flex items-center gap-6">
            <div className="relative h-20 w-20">
              <svg className="h-20 w-20 -rotate-90" viewBox="0 0 36 36">
                <path
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke="#27272a"
                  strokeWidth="3"
                />
                <path
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke="#34d399"
                  strokeWidth="3"
                  strokeDasharray={`${avgProgress}, 100`}
                />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-sm font-medium">
                {avgProgress}%
              </span>
            </div>
            <div className="text-sm text-zinc-400">
              <div>
                <span className="text-white font-medium">{sessions.length}</span> prep sessions
              </div>
              <div className="mt-1">Average completion across plans</div>
            </div>
          </div>
        </div>

        <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-medium">Recent sessions</h2>
            <Link to="/progress" className="text-xs text-zinc-400 hover:text-white">
              View all
            </Link>
          </div>
          {loading && <p className="text-sm text-zinc-500">Loading…</p>}
          {!loading && sessions.length === 0 && (
            <p className="text-sm text-zinc-500">
              No sessions yet.{' '}
              <Link to="/resume" className="text-white underline">
                Tailor a resume
              </Link>{' '}
              to start.
            </p>
          )}
          <ul className="space-y-2">
            {sessions.slice(0, 5).map((s) => (
              <li key={s.id}>
                <Link
                  to={`/sessions/${s.id}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-zinc-900/50 border border-zinc-800/80 hover:border-zinc-700 transition"
                >
                  <div>
                    <div className="text-sm font-medium">{s.title || `Session #${s.id}`}</div>
                    <div className="text-xs text-zinc-500 capitalize">{s.status}</div>
                  </div>
                  <span className="text-xs text-zinc-400">{Math.round(s.progress_pct || 0)}%</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
