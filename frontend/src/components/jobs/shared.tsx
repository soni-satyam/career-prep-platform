import { useState } from 'react'
import type { JobResult, JobSearchParams } from '../../lib/api'

export const PAGE_SIZE = 20

export const SOURCES: Array<{ key: string; label: string }> = [
  { key: 'career_page', label: 'Company career pages' },
  { key: 'greenhouse', label: 'Greenhouse' },
  { key: 'lever', label: 'Lever' },
  { key: 'ashby', label: 'Ashby' },
  { key: 'workable', label: 'Workable' },
  { key: 'smartrecruiters', label: 'SmartRecruiters' },
  { key: 'recruitee', label: 'Recruitee' },
  { key: 'linkedin', label: 'LinkedIn' },
  { key: 'naukri', label: 'Naukri' },
  { key: 'indeed', label: 'Indeed' },
  { key: 'glassdoor', label: 'Glassdoor' },
  { key: 'wellfound', label: 'Wellfound' },
  { key: 'web', label: 'Web search' },
  { key: 'other', label: 'Other portals' },
]

export const TIER_STYLE: Record<string, string> = {
  career_page: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  greenhouse: 'bg-teal-500/15 text-teal-300 border-teal-500/30',
  lever: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  ashby: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  workable: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  smartrecruiters: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  recruitee: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  web: 'bg-zinc-700/40 text-zinc-300 border-zinc-600',
  linkedin: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  naukri: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  indeed: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
}

export interface Filters {
  q: string
  location: string
  work_mode: string
  salary: string // amount typed by the user (LPA for INR, thousands otherwise)
  currency: string
  includeNoSalary: boolean
  expMin: string
  expMax: string
  employment_type: string
  posted: string
  sources: string[]
  sort: string
}

export const DEFAULT_FILTERS: Filters = {
  q: '',
  location: '',
  work_mode: '',
  salary: '',
  currency: 'INR',
  includeNoSalary: true,
  expMin: '',
  expMax: '',
  employment_type: '',
  posted: '',
  sources: [],
  sort: 'priority',
}

export function toParams(f: Filters, page: number): JobSearchParams {
  const salaryNum = parseFloat(f.salary)
  const hasSalary = Number.isFinite(salaryNum) && salaryNum > 0
  const num = (s: string) => (s.trim() !== '' && Number.isFinite(parseFloat(s)) ? parseFloat(s) : undefined)
  return {
    q: f.q.trim() || undefined,
    location: f.location.trim() || undefined,
    work_mode: f.work_mode || undefined,
    // INR is typed in lakhs per annum, other currencies in thousands per year
    salary_min: hasSalary ? Math.round(salaryNum * (f.currency === 'INR' ? 100_000 : 1_000)) : undefined,
    salary_currency: hasSalary ? f.currency : undefined,
    include_unspecified_salary: hasSalary ? f.includeNoSalary : undefined,
    experience_min: num(f.expMin),
    experience_max: num(f.expMax),
    employment_type: f.employment_type || undefined,
    posted_within_days: f.posted ? parseInt(f.posted, 10) : undefined,
    sources: f.sources.length ? f.sources : undefined,
    sort: f.sort,
    page,
    page_size: PAGE_SIZE,
  }
}

export const WORK_MODE_LABEL: Record<string, string> = { remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site' }
export const TYPE_LABEL: Record<string, string> = {
  'full-time': 'Full-time',
  'part-time': 'Part-time',
  contract: 'Contract',
  internship: 'Internship',
}
export const POSTED_LABEL: Record<string, string> = {
  '1': 'Last 24 hours',
  '3': 'Last 3 days',
  '7': 'Last week',
  '14': 'Last 2 weeks',
  '30': 'Last month',
}

// One chip per filter that is actually applied to the current results.
export function activeChips(f: Filters): Array<{ key: string; label: string; clear: Partial<Filters> }> {
  const chips: Array<{ key: string; label: string; clear: Partial<Filters> }> = []
  if (f.work_mode) chips.push({ key: 'work_mode', label: WORK_MODE_LABEL[f.work_mode] ?? f.work_mode, clear: { work_mode: '' } })
  if (f.employment_type)
    chips.push({ key: 'type', label: TYPE_LABEL[f.employment_type] ?? f.employment_type, clear: { employment_type: '' } })
  if (f.posted) chips.push({ key: 'posted', label: POSTED_LABEL[f.posted] ?? `Last ${f.posted} days`, clear: { posted: '' } })
  if (f.salary.trim() && parseFloat(f.salary) > 0)
    chips.push({
      key: 'salary',
      label: `Salary ≥ ${f.salary}${f.currency === 'INR' ? 'L' : 'k'} ${f.currency}${f.includeNoSalary ? '' : ' (listed only)'}`,
      clear: { salary: '' },
    })
  if (f.expMin.trim() || f.expMax.trim())
    chips.push({
      key: 'exp',
      label: `Exp ${f.expMin.trim() || '0'}–${f.expMax.trim() || '∞'} yrs`,
      clear: { expMin: '', expMax: '' },
    })
  if (f.sources.length)
    chips.push({
      key: 'sources',
      label: f.sources.map((k) => SOURCES.find((x) => x.key === k)?.label ?? k).join(', '),
      clear: { sources: [] },
    })
  return chips
}

export function timeAgo(iso: string | null): string {
  if (!iso) return 'Date not listed'
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3_600_000)
  if (h < 1) return 'Just now'
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return d === 1 ? '1 day ago' : `${d} days ago`
  const m = Math.floor(d / 30)
  return m === 1 ? '1 month ago' : `${m} months ago`
}

export function money(n: number, cur: string): string {
  if (cur === 'INR') return n >= 100_000 ? `₹${+(n / 100_000).toFixed(1)}L` : `₹${Math.round(n).toLocaleString('en-IN')}`
  const sym: Record<string, string> = { USD: '$', EUR: '€', GBP: '£' }
  const s = sym[cur] ?? `${cur} `
  return n >= 1000 ? `${s}${Math.round(n / 1000)}k` : `${s}${Math.round(n)}`
}

export function salaryText(j: JobResult): string {
  if (j.salary_min == null && j.salary_max == null) return j.salary_text
  const cur = j.salary_currency || ''
  if (j.salary_min != null && j.salary_max != null && j.salary_min !== j.salary_max)
    return `${money(j.salary_min, cur)} – ${money(j.salary_max, cur)} / yr`
  return `${money((j.salary_max ?? j.salary_min) as number, cur)} / yr`
}

export function expText(j: JobResult): string {
  const { experience_min: lo, experience_max: hi } = j
  if (lo == null && hi == null) return ''
  if (lo != null && hi != null) return `${lo}–${hi} yrs exp`
  if (lo != null) return `${lo}+ yrs exp`
  return `up to ${hi} yrs exp`
}

export const inputCls =
  'w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600'

export function MatchPill({ job }: { job: JobResult }) {
  const [open, setOpen] = useState(false)
  if (!job.match) return null
  const s = job.match.score
  const tone =
    s >= 75
      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
      : s >= 50
        ? 'bg-amber-500/15 text-amber-300 border-amber-500/40'
        : 'bg-zinc-800 text-zinc-300 border-zinc-700'
  return (
    <div className="text-right shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`border rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}
        title="How well your profile matches this job. Click for details."
      >
        {s}% match
      </button>
      {open && (
        <div className="mt-2 text-left text-xs bg-[#0c0c0e] border border-zinc-800 rounded-lg p-3 w-64 absolute right-4 z-10 shadow-xl">
          {job.match.matched_skills.length > 0 && (
            <div className="mb-2">
              <div className="text-zinc-500 mb-1">You have</div>
              <div className="flex flex-wrap gap-1">
                {job.match.matched_skills.map((s) => (
                  <span key={s} className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
          {job.match.missing_skills.length > 0 && (
            <div>
              <div className="text-zinc-500 mb-1">Worth adding</div>
              <div className="flex flex-wrap gap-1">
                {job.match.missing_skills.map((s) => (
                  <span key={s} className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
          {job.match.matched_skills.length === 0 && job.match.missing_skills.length === 0 && (
            <div className="text-zinc-500">Based on job title and experience (no skills listed in the posting).</div>
          )}
        </div>
      )}
    </div>
  )
}

export function JobCard({ job }: { job: JobResult }) {
  const sal = salaryText(job)
  const exp = expText(job)
  const mode = job.work_mode || (job.remote ? 'remote' : '')
  return (
    <div className="relative bg-[#111113] border border-zinc-800 rounded-xl p-4 hover:border-zinc-600 transition">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-sm hover:underline break-words"
          >
            {job.title}
          </a>
          <div className="text-xs text-zinc-400 mt-1">
            {job.company || 'Company'}
            {job.location ? ` · ${job.location}` : ''}
            {mode ? ` · ${mode}` : ''}
          </div>
        </div>
        <MatchPill job={job} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5 mt-3 text-xs">
        <span
          className={`border rounded px-1.5 py-0.5 ${TIER_STYLE[job.source] ?? 'bg-zinc-800 text-zinc-300 border-zinc-700'}`}
        >
          {job.source_label}
        </span>
        <span className="text-zinc-500">{timeAgo(job.posted_at)}</span>
        {sal && <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-200">{sal}</span>}
        {exp && <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300">{exp}</span>}
        {job.employment_type && (
          <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300">{job.employment_type}</span>
        )}
      </div>

      {job.snippet && <p className="text-sm text-zinc-400 mt-3 line-clamp-2">{job.snippet}</p>}

      <div className="flex items-center justify-between mt-3">
        <div className="text-xs text-zinc-500">
          {job.also_on.length > 0 && (
            <>
              Also on{' '}
              {job.also_on.map((a, i) => (
                <span key={a.source}>
                  {i > 0 && ', '}
                  <a href={a.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-zinc-300">
                    {a.label}
                  </a>
                </span>
              ))}
            </>
          )}
        </div>
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="bg-white text-black text-xs font-medium px-3 py-1.5 rounded-md"
        >
          Apply
        </a>
      </div>
    </div>
  )
}
