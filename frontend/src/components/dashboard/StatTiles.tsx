import { Link } from 'react-router-dom'
import { Bookmark, Briefcase, GraduationCap, MessagesSquare, Trophy } from 'lucide-react'
import type { DashboardData } from '../../lib/dashboardApi'

export default function StatTiles({ stats }: { stats: DashboardData['stats'] }) {
  const tiles = [
    { label: 'Saved jobs', value: stats.saved_jobs, icon: Bookmark, tone: 'text-blue-400 bg-blue-500/15', to: '/jobs' },
    { label: 'Active applications', value: stats.active, icon: Briefcase, tone: 'text-sky-400 bg-sky-500/15', to: null },
    { label: 'Interviewing', value: stats.interviewing, icon: MessagesSquare, tone: 'text-amber-400 bg-amber-500/15', to: null },
    { label: 'Offers', value: stats.offers, icon: Trophy, tone: 'text-emerald-400 bg-emerald-500/15', to: null },
    { label: 'Prep sessions', value: stats.prep_sessions, icon: GraduationCap, tone: 'text-violet-400 bg-violet-500/15', to: '/progress' },
  ]
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {tiles.map(({ label, value, icon: Icon, tone, to }) => {
        const body = (
          <div className="bg-[#111113] border border-zinc-800 rounded-xl p-4 hover:border-zinc-700 transition h-full">
            <div className={`h-8 w-8 rounded-lg flex items-center justify-center mb-3 ${tone}`}>
              <Icon size={16} strokeWidth={1.75} />
            </div>
            <div className="text-2xl font-semibold leading-none">{value}</div>
            <div className="text-xs text-zinc-500 mt-1.5">{label}</div>
          </div>
        )
        return to ? (
          <Link key={label} to={to}>
            {body}
          </Link>
        ) : (
          <div key={label}>{body}</div>
        )
      })}
    </div>
  )
}
