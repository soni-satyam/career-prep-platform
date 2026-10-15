import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { dashboardApi, type RecommendedData, type TrackableJob } from '../../lib/dashboardApi'
import { seedJobState } from '../../lib/jobState'
import JobActions from './JobActions'
import { card, timeAgo } from './format'

function matchTone(s: number) {
  return s >= 75
    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
    : s >= 50
      ? 'bg-amber-500/15 text-amber-300 border-amber-500/40'
      : 'bg-zinc-800 text-zinc-300 border-zinc-700'
}

function Job({ job }: { job: TrackableJob }) {
  return (
    <div className="rounded-lg bg-zinc-900/50 border border-zinc-800/80 p-3.5 hover:border-zinc-700 transition flex flex-col">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <a href={job.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium hover:underline inline-flex items-start gap-1">
            <span className="break-words">{job.title}</span>
            <ExternalLink size={12} className="mt-1 shrink-0 text-zinc-500" />
          </a>
          <div className="text-xs text-zinc-500 mt-0.5">{[job.company, job.location].filter(Boolean).join(' · ')}</div>
        </div>
        {job.match && (
          <span className={`border rounded-full px-2 py-0.5 text-xs font-semibold shrink-0 ${matchTone(job.match.score)}`}>{job.match.score}%</span>
        )}
      </div>
      <div className="text-xs text-zinc-500 mt-2">
        {job.source_label}
        {job.posted_at ? ` · ${timeAgo(job.posted_at)}` : ''}
      </div>
      {job.match && job.match.matched_skills.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {job.match.matched_skills.slice(0, 4).map((s) => (
            <span key={s} className="text-[11px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300">
              {s}
            </span>
          ))}
        </div>
      )}
      <div className="mt-3 pt-3 border-t border-zinc-800/80">
        <JobActions job={job} />
      </div>
    </div>
  )
}

export default function RecommendedJobs({ hasResume }: { hasResume: boolean }) {
  const [data, setData] = useState<RecommendedData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const r = await dashboardApi.recommended(6)
      seedJobState(r.saved_ids, r.applied_ids)
      setData(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load recommendations')
    } finally {
      setLoading(false)
    }
  }, [])

  // reload when the resume appears/changes
  useEffect(() => {
    load()
  }, [load, hasResume])

  return (
    <div className={card}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-medium">Recommended for you</h2>
          {data?.reason === 'ok' && <p className="text-xs text-zinc-500 mt-0.5">Best matches for {data.based_on}, posted recently.</p>}
        </div>
        <button onClick={load} disabled={loading} className="text-zinc-500 hover:text-white disabled:opacity-50" aria-label="Refresh recommendations" title="Refresh">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {loading && !data && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-32 rounded-lg bg-zinc-900/50 border border-zinc-800/80 animate-pulse" />
          ))}
        </div>
      )}
      {error && <p className="text-sm text-red-400">{error}</p>}
      {data?.reason === 'no_resume' && (
        <p className="text-sm text-zinc-400">
          Upload your resume and we’ll rank open jobs by how well you match.{' '}
          <span className="text-zinc-500">Use “Upload resume” above.</span>
        </p>
      )}
      {data?.reason === 'no_results' && (
        <p className="text-sm text-zinc-400">
          Nothing strong enough to recommend right now.{' '}
          <Link to="/jobs" className="text-white underline">
            Search jobs
          </Link>{' '}
          to widen the net, or check that your job sources are set up.
        </p>
      )}
      {data?.reason === 'ok' && (
        <div className={`grid sm:grid-cols-2 lg:grid-cols-3 gap-3 ${loading ? 'opacity-60' : ''}`}>
          {data.jobs.map((j) => (
            <Job key={j.id} job={j} />
          ))}
        </div>
      )}
    </div>
  )
}
