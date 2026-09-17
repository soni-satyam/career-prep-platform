import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import type { AtsMatch } from '../lib/api'
import CircularMeter from './CircularMeter'

export default function AtsMatchMeter({ match }: { match: AtsMatch }) {
  const [open, setOpen] = useState(false)
  const { before, after, delta } = match

  return (
    <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5 sm:p-6">
      <div className="mb-5">
        <h2 className="font-medium">Job description match</h2>
        <p className="text-xs text-zinc-500 mt-0.5">
          Share of the {after.total_terms} skills and requirements in the job description that your resume mentions.
        </p>
      </div>

      <div className="flex items-center justify-center gap-4 sm:gap-10 flex-wrap">
        {before && <CircularMeter value={before.score} label="Original resume" />}
        {before && (
          <div className="flex flex-col items-center gap-2">
            <ArrowRight className="text-zinc-600 hidden sm:block" size={28} />
            {delta != null && (
              <span
                className={`text-sm font-semibold px-3 py-1 rounded-full border ${
                  delta > 0
                    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
                    : delta < 0
                      ? 'bg-red-500/15 text-red-300 border-red-500/40'
                      : 'bg-zinc-800 text-zinc-300 border-zinc-700'
                }`}
              >
                {delta > 0 ? `+${delta}` : delta} points
              </span>
            )}
          </div>
        )}
        <CircularMeter value={after.score} label="Tailored resume" />
      </div>

      {(match.gained.length > 0 || match.still_missing.length > 0) && (
        <div className="mt-6 border-t border-zinc-800 pt-4">
          <button type="button" onClick={() => setOpen((o) => !o)} className="text-xs text-zinc-400 underline">
            {open ? 'Hide keyword details' : 'Show keyword details'}
          </button>
          {open && (
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <div>
                <div className="text-xs text-zinc-500 mb-1.5">Added by tailoring ({match.gained.length})</div>
                <div className="flex flex-wrap gap-1">
                  {match.gained.length === 0 && <span className="text-xs text-zinc-600">Nothing new</span>}
                  {match.gained.map((k) => (
                    <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300">
                      {k}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-xs text-zinc-500 mb-1.5">
                  Still missing ({match.still_missing.length}) — add only if true for you
                </div>
                <div className="flex flex-wrap gap-1">
                  {match.still_missing.length === 0 && <span className="text-xs text-zinc-600">Nothing missing</span>}
                  {match.still_missing.map((k) => (
                    <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300">
                      {k}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      <p className="text-[11px] text-zinc-600 mt-4">
        An estimate from {match.method}. Real applicant tracking systems differ, so treat it as a guide.
      </p>
    </div>
  )
}
