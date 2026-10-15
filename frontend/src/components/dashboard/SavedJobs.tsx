import { Link } from 'react-router-dom'
import { ExternalLink, X } from 'lucide-react'
import { trackerApi, type SavedJob } from '../../lib/dashboardApi'
import { markApplied, toggleSaved, useJobState } from '../../lib/jobState'
import { card, timeAgo } from './format'

export default function SavedJobs({ jobs, total, onChanged }: { jobs: SavedJob[]; total: number; onChanged: () => void }) {
  const { applied } = useJobState()

  const asTrackable = (j: SavedJob) => ({
    id: j.job_uid,
    title: j.title,
    company: j.company,
    location: j.location,
    url: j.url,
    source: j.source,
    source_label: j.source_label,
    posted_at: j.posted_at,
    salary_text: j.salary_text,
    match: j.match_score != null ? { score: Math.round(j.match_score), matched_skills: [], missing_skills: [] } : null,
  })

  return (
    <div className={card}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-medium">
          Saved jobs <span className="text-zinc-600 font-normal text-sm">{total}</span>
        </h2>
        <Link to="/jobs" className="text-xs text-zinc-400 hover:text-white">
          Find more
        </Link>
      </div>
      {jobs.length === 0 && (
        <p className="text-sm text-zinc-500">
          Bookmark jobs while you search and they’ll show up here.{' '}
          <Link to="/jobs" className="text-white underline">
            Search jobs
          </Link>
        </p>
      )}
      <ul className="space-y-2">
        {jobs.map((j) => (
          <li key={j.id} className="rounded-lg bg-zinc-900/50 border border-zinc-800/80 p-3 flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <a href={j.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium truncate hover:underline">
                  {j.title}
                </a>
                <ExternalLink size={12} className="text-zinc-500 shrink-0" />
              </div>
              <div className="text-xs text-zinc-500 truncate">
                {[j.company, j.location, j.source_label].filter(Boolean).join(' · ')} · saved {timeAgo(j.created_at)}
              </div>
              <div className="mt-2 flex items-center gap-2">
                {j.match_score != null && <span className="text-xs text-emerald-300">{Math.round(j.match_score)}% match</span>}
                <button
                  disabled={applied.has(j.job_uid)}
                  onClick={async () => {
                    await markApplied(asTrackable(j)).catch(() => undefined)
                    onChanged()
                  }}
                  className="text-xs border border-zinc-700 rounded-md px-2 py-1 hover:border-zinc-500 disabled:opacity-50 disabled:cursor-default"
                >
                  {applied.has(j.job_uid) ? 'Tracking' : 'I applied'}
                </button>
              </div>
            </div>
            <button
              onClick={async () => {
                await toggleSaved(asTrackable(j)).catch(() => trackerApi.unsave(j.job_uid))
                onChanged()
              }}
              className="text-zinc-500 hover:text-white"
              aria-label={`Remove ${j.title} from saved`}
              title="Remove"
            >
              <X size={15} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
