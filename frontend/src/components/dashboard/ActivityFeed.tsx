import { Link } from 'react-router-dom'
import { ArrowRightLeft, Bookmark, FileText, GraduationCap, Send, Sparkles } from 'lucide-react'
import type { ActivityItem } from '../../lib/dashboardApi'
import { card, timeAgo } from './format'

const ICON: Record<string, { icon: typeof FileText; tone: string }> = {
  resume_uploaded: { icon: FileText, tone: 'text-emerald-400 bg-emerald-500/15' },
  job_saved: { icon: Bookmark, tone: 'text-blue-400 bg-blue-500/15' },
  application_added: { icon: Send, tone: 'text-sky-400 bg-sky-500/15' },
  application_status: { icon: ArrowRightLeft, tone: 'text-amber-400 bg-amber-500/15' },
  session: { icon: GraduationCap, tone: 'text-violet-400 bg-violet-500/15' },
}

export default function ActivityFeed({ items }: { items: ActivityItem[] }) {
  return (
    <div className={card}>
      <h2 className="font-medium mb-4">Recent activity</h2>
      {items.length === 0 && <p className="text-sm text-zinc-500">Your activity will show up here as you use the app.</p>}
      <ul className="space-y-1">
        {items.map((it) => {
          const { icon: Icon, tone } = ICON[it.type] ?? { icon: Sparkles, tone: 'text-zinc-400 bg-zinc-800' }
          const row = (
            <div className="flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-900/60 transition">
              <div className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 ${tone}`}>
                <Icon size={15} strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm truncate">{it.title}</div>
                {it.subtitle && <div className="text-xs text-zinc-500 truncate">{it.subtitle}</div>}
              </div>
              <div className="text-xs text-zinc-600 shrink-0">{timeAgo(it.at)}</div>
            </div>
          )
          return <li key={it.id}>{it.link ? <Link to={it.link}>{row}</Link> : row}</li>
        })}
      </ul>
    </div>
  )
}
