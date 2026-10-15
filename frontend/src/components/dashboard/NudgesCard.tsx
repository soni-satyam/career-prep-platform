import { CalendarClock, MailQuestion } from 'lucide-react'
import { trackerApi, type Application } from '../../lib/dashboardApi'
import { card, dayDelta, timeAgo } from './format'

/** Coming up (next steps with dates) and applications that have gone quiet. */
export default function NudgesCard({
  upcoming,
  followUp,
  onChanged,
}: {
  upcoming: Application[]
  followUp: Application[]
  onChanged: () => void
}) {
  if (upcoming.length === 0 && followUp.length === 0) return null
  return (
    <div className={card}>
      {upcoming.length > 0 && (
        <div className={followUp.length ? 'mb-5' : ''}>
          <h2 className="font-medium mb-3 flex items-center gap-2">
            <CalendarClock size={16} className="text-amber-400" /> Coming up
          </h2>
          <ul className="space-y-2">
            {upcoming.map((a) => (
              <li key={a.id} className="text-sm flex items-baseline justify-between gap-3">
                <span className="truncate">
                  {a.next_step || 'Next step'} <span className="text-zinc-500">· {a.title}{a.company ? `, ${a.company}` : ''}</span>
                </span>
                <span className="text-xs text-amber-300 shrink-0">{dayDelta(a.next_step_date)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {followUp.length > 0 && (
        <div>
          <h2 className="font-medium mb-1 flex items-center gap-2">
            <MailQuestion size={16} className="text-sky-400" /> Time to follow up
          </h2>
          <p className="text-xs text-zinc-500 mb-3">No movement for over 10 days.</p>
          <ul className="space-y-2">
            {followUp.map((a) => (
              <li key={a.id} className="text-sm flex items-center justify-between gap-3">
                <span className="truncate">
                  {a.title} <span className="text-zinc-500">· {a.company || 'company'} · {timeAgo(a.updated_at)}</span>
                </span>
                <button
                  onClick={async () => {
                    await trackerApi.updateApplication(a.id, { next_step: 'Followed up' }).catch(() => undefined)
                    onChanged()
                  }}
                  className="text-xs border border-zinc-700 rounded-md px-2 py-1 hover:border-zinc-500 shrink-0"
                >
                  I followed up
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
