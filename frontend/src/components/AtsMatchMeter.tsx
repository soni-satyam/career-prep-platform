import { useEffect, useState } from 'react'
import type { AtsMatch } from '../lib/api'

function tone(score: number) {
  if (score >= 75) return { bar: 'bg-emerald-500', text: 'text-emerald-300', label: 'Strong match' }
  if (score >= 50) return { bar: 'bg-amber-500', text: 'text-amber-300', label: 'Moderate match' }
  return { bar: 'bg-red-500', text: 'text-red-300', label: 'Weak match' }
}

function Bar({ label, score, animate }: { label: string; score: number; animate: boolean }) {
  const t = tone(score)
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-sm text-zinc-300">{label}</span>
        <span className={`text-2xl font-semibold tabular-nums ${t.text}`}>{score}%</span>
      </div>
      <div
        className="h-2.5 rounded-full bg-zinc-800 overflow-hidden"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
      >
        <div
          className={`h-full rounded-full ${t.bar} transition-[width] duration-1000 ease-out`}
          style={{ width: animate ? `${score}%` : '0%' }}
        />
      </div>
      <div className="text-xs text-zinc-500 mt-1">{t.label}</div>
    </div>
  )
}

export default function AtsMatchMeter({ match }: { match: AtsMatch }) {
  const [animate, setAnimate] = useState(false)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setAnimate(true))
    return () => cancelAnimationFrame(id)
  }, [])

  const { before, after, delta } = match
  return (
    <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
        <div>
          <h2 className="font-medium">Job description match</h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            How much of what this job asks for appears in your resume ({after.total_terms} skills &amp; requirements checked).
          </p>
        </div>
        {delta != null && (
          <span
            className={`text-sm font-semibold px-2.5 py-1 rounded-full border ${
              delta > 0
                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
                : 'bg-zinc-800 text-zinc-300 border-zinc-700'
            }`}
          >
            {delta > 0 ? `+${delta}` : delta} points
          </span>
        )}
      </div>

      <div className={`grid gap-6 ${before ? 'sm:grid-cols-2' : ''}`}>
        {before && <Bar label="Your original resume" score={before.score} animate={animate} />}
        <Bar label="Tailored resume" score={after.score} animate={animate} />
      </div>

      {(match.gained.length > 0 || match.still_missing.length > 0) && (
        <div className="mt-4">
          <button type="button" onClick={() => setOpen((o) => !o)} className="text-xs text-zinc-400 underline">
            {open ? 'Hide keyword details' : 'Show keyword details'}
          </button>
          {open && (
            <div className="mt-3 space-y-3">
              {match.gained.length > 0 && (
                <div>
                  <div className="text-xs text-zinc-500 mb-1">Added by tailoring ({match.gained.length})</div>
                  <div className="flex flex-wrap gap-1">
                    {match.gained.map((k) => (
                      <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300">
                        {k}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {match.still_missing.length > 0 && (
                <div>
                  <div className="text-xs text-zinc-500 mb-1">
                    Still missing ({match.still_missing.length}) — add these only if they are true for you
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {match.still_missing.map((k) => (
                      <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300">
                        {k}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      <p className="text-[11px] text-zinc-600 mt-4">
        An estimate based on {match.method}. Real applicant tracking systems differ, so treat it as a guide.
      </p>
    </div>
  )
}
