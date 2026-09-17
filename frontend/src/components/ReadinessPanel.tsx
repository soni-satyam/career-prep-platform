import { useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleAlert, Lightbulb, ShieldCheck, XCircle } from 'lucide-react'
import type { ReadinessVerdict } from '../lib/api'

interface Gap {
  id?: string
  type?: string
  severity?: string
  description?: string
  how_to_close?: string
  related_skills?: string[]
}
interface GapAnalysis {
  overall_readiness?: string
  gaps?: Gap[]
  strengths?: string[]
}

const LEVEL: Record<string, { ring: string; chip: string; Icon: typeof CheckCircle2 }> = {
  ready: { ring: 'border-emerald-500/50 text-emerald-300 bg-emerald-500/10', chip: 'text-emerald-300', Icon: ShieldCheck },
  almost: { ring: 'border-sky-500/50 text-sky-300 bg-sky-500/10', chip: 'text-sky-300', Icon: CheckCircle2 },
  needs_work: { ring: 'border-amber-500/50 text-amber-300 bg-amber-500/10', chip: 'text-amber-300', Icon: AlertTriangle },
  significant_gap: { ring: 'border-red-500/50 text-red-300 bg-red-500/10', chip: 'text-red-300', Icon: XCircle },
}

// Used only for older sessions that have no computed verdict.
const FALLBACK: Record<string, { label: string; headline: string }> = {
  ready: { label: 'Ready to apply', headline: 'Your resume covers what this job asks for.' },
  almost: { label: 'Almost there', headline: 'A few gaps are worth closing first.' },
  needs_work: { label: 'Needs work', headline: 'Important requirements are missing or weak.' },
  significant_gap: { label: 'Significant gaps', headline: 'This role asks for a lot your resume does not show yet.' },
}

const SEVERITY: Record<string, { label: string; cls: string; bar: string; rank: number }> = {
  high: { label: 'High priority', cls: 'bg-red-500/15 text-red-300', bar: 'border-l-red-500', rank: 0 },
  medium: { label: 'Medium', cls: 'bg-amber-500/15 text-amber-300', bar: 'border-l-amber-500', rank: 1 },
  low: { label: 'Low', cls: 'bg-zinc-800 text-zinc-300', bar: 'border-l-zinc-600', rank: 2 },
}

const TYPE_LABEL: Record<string, string> = {
  missing_skill: 'Missing skill',
  missing_experience: 'Missing experience',
  no_quantification: 'Add numbers & results',
  low_relevance: 'Low relevance',
}

const TONE_DOT: Record<string, string> = { good: 'bg-emerald-400', ok: 'bg-amber-400', bad: 'bg-red-400' }

export default function ReadinessPanel({
  readiness,
  analysis,
}: {
  readiness: ReadinessVerdict | null
  analysis: GapAnalysis | null
}) {
  const [allGaps, setAllGaps] = useState(false)
  const [allStrengths, setAllStrengths] = useState(false)

  const gaps = [...(analysis?.gaps ?? [])]
    .filter((g) => g.description)
    .sort((a, b) => (SEVERITY[a.severity ?? 'medium']?.rank ?? 1) - (SEVERITY[b.severity ?? 'medium']?.rank ?? 1))
  const strengths = (analysis?.strengths ?? []).filter(Boolean)

  const level = readiness?.level ?? analysis?.overall_readiness ?? 'needs_work'
  const style = LEVEL[level] ?? LEVEL.needs_work
  const copy = readiness ?? { ...(FALLBACK[level] ?? FALLBACK.needs_work), factors: [], counts: null }
  const counts = readiness?.counts ?? {
    high: gaps.filter((g) => g.severity === 'high').length,
    medium: gaps.filter((g) => g.severity === 'medium').length,
    low: gaps.filter((g) => g.severity === 'low').length,
  }
  const Icon = style.Icon

  const shownGaps = allGaps ? gaps : gaps.slice(0, 4)
  const shownStrengths = allStrengths ? strengths : strengths.slice(0, 4)

  return (
    <div className="bg-[#111113] border border-zinc-800 rounded-xl overflow-hidden">
      {/* verdict */}
      <div className="p-5 sm:p-6 flex items-start gap-4 flex-wrap">
        <div className={`w-14 h-14 shrink-0 rounded-full border flex items-center justify-center ${style.ring}`}>
          <Icon size={28} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs uppercase tracking-wide text-zinc-500">Readiness for this job</div>
          <div className={`text-2xl font-semibold ${style.chip}`}>{copy.label}</div>
          <p className="text-sm text-zinc-400 mt-1 max-w-xl">{copy.headline}</p>
        </div>
        {(counts.high > 0 || counts.medium > 0 || counts.low > 0) && (
          <div className="flex gap-2 text-xs">
            {counts.high > 0 && <span className="px-2 py-1 rounded-md bg-red-500/15 text-red-300">{counts.high} high</span>}
            {counts.medium > 0 && (
              <span className="px-2 py-1 rounded-md bg-amber-500/15 text-amber-300">{counts.medium} medium</span>
            )}
            {counts.low > 0 && <span className="px-2 py-1 rounded-md bg-zinc-800 text-zinc-300">{counts.low} low</span>}
          </div>
        )}
      </div>

      {/* why */}
      {readiness && readiness.factors.length > 0 && (
        <div className="px-5 sm:px-6 pb-5">
          <div className="text-xs text-zinc-500 mb-2">Why this verdict</div>
          <ul className="space-y-1.5">
            {readiness.factors.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${TONE_DOT[f.tone]}`} />
                {f.text}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(strengths.length > 0 || gaps.length > 0) && (
        <div className="border-t border-zinc-800 grid lg:grid-cols-5">
          {/* strengths */}
          <div className="p-5 sm:p-6 lg:col-span-2 lg:border-r border-zinc-800">
            <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
              <CheckCircle2 size={16} className="text-emerald-400" /> What you already have
            </h3>
            {strengths.length === 0 ? (
              <p className="text-sm text-zinc-500">No clear strengths were identified for this role.</p>
            ) : (
              <ul className="space-y-2">
                {shownStrengths.map((s, i) => (
                  <li key={i} className="text-sm text-zinc-300 flex gap-2">
                    <span className="text-emerald-400 shrink-0">✓</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            )}
            {strengths.length > 4 && (
              <button className="text-xs text-zinc-400 underline mt-3" onClick={() => setAllStrengths((v) => !v)}>
                {allStrengths ? 'Show fewer' : `Show all ${strengths.length}`}
              </button>
            )}
          </div>

          {/* gaps */}
          <div className="p-5 sm:p-6 lg:col-span-3 border-t lg:border-t-0 border-zinc-800">
            <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
              <CircleAlert size={16} className="text-amber-400" /> What to work on
            </h3>
            {gaps.length === 0 ? (
              <p className="text-sm text-zinc-500">No gaps were flagged against this job.</p>
            ) : (
              <div className="space-y-3">
                {shownGaps.map((g, i) => {
                  const sev = SEVERITY[g.severity ?? 'medium'] ?? SEVERITY.medium
                  return (
                    <div key={g.id ?? i} className={`border border-zinc-800 border-l-4 ${sev.bar} rounded-lg p-3.5 bg-[#0c0c0e]`}>
                      <div className="flex items-center gap-2 flex-wrap mb-1.5">
                        <span className={`text-[11px] px-1.5 py-0.5 rounded ${sev.cls}`}>{sev.label}</span>
                        <span className="text-[11px] text-zinc-500">{TYPE_LABEL[g.type ?? ''] ?? 'Gap'}</span>
                      </div>
                      <p className="text-sm text-zinc-200">{g.description}</p>
                      {g.how_to_close && (
                        <p className="text-xs text-zinc-400 mt-2 flex gap-1.5">
                          <Lightbulb size={14} className="text-amber-400 shrink-0 mt-px" />
                          <span>{g.how_to_close}</span>
                        </p>
                      )}
                      {g.related_skills && g.related_skills.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {g.related_skills.map((s) => (
                            <span key={s} className="text-[11px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300">
                              {s}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            {gaps.length > 4 && (
              <button className="text-xs text-zinc-400 underline mt-3" onClick={() => setAllGaps((v) => !v)}>
                {allGaps ? 'Show top 4 only' : `Show all ${gaps.length} gaps`}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
