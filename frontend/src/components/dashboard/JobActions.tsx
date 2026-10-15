import { useEffect, useState } from 'react'
import { Bookmark, BookmarkCheck, Check, Send } from 'lucide-react'
import { type TrackableJob } from '../../lib/dashboardApi'
import { loadJobState, markApplied, toggleSaved, useJobState } from '../../lib/jobState'

/** Save + "I applied" buttons for any job card (dashboard and Jobs page share the same state). */
export default function JobActions({ job, compact = false }: { job: TrackableJob; compact?: boolean }) {
  const { saved, applied } = useJobState()
  const [err, setErr] = useState('')
  const isSaved = saved.has(job.id)
  const isApplied = applied.has(job.id)

  useEffect(() => {
    loadJobState()
  }, [])

  const run = async (fn: () => Promise<void>) => {
    setErr('')
    try {
      await fn()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Something went wrong')
    }
  }

  const btn = 'inline-flex items-center gap-1.5 border rounded-md text-xs px-2.5 py-1.5 transition'
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        type="button"
        onClick={() => run(() => toggleSaved(job))}
        className={`${btn} ${isSaved ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' : 'border-zinc-700 text-zinc-300 hover:border-zinc-500'}`}
        title={isSaved ? 'Remove from saved jobs' : 'Save for later'}
        aria-pressed={isSaved}
      >
        {isSaved ? <BookmarkCheck size={14} /> : <Bookmark size={14} />}
        {compact ? null : isSaved ? 'Saved' : 'Save'}
      </button>
      <button
        type="button"
        disabled={isApplied}
        onClick={() => run(() => markApplied(job))}
        className={`${btn} ${isApplied ? 'border-sky-500/40 text-sky-300 bg-sky-500/10 cursor-default' : 'border-zinc-700 text-zinc-300 hover:border-zinc-500'}`}
        title={isApplied ? 'In your application tracker' : 'Add to your application tracker'}
      >
        {isApplied ? <Check size={14} /> : <Send size={14} />}
        {compact ? null : isApplied ? 'Tracking' : 'I applied'}
      </button>
      {err && <span className="text-xs text-red-400">{err}</span>}
    </div>
  )
}
