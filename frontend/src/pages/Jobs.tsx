import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  jobsApi,
  profileApi,
  type CandidateProfile,
  type JobResult,
  type JobSearchParams,
  type JobSearchResponse,
} from '../lib/api'

const PAGE_SIZE = 20

const SOURCES: Array<{ key: string; label: string }> = [
  { key: 'career_page', label: 'Company career pages' },
  { key: 'greenhouse', label: 'Greenhouse' },
  { key: 'lever', label: 'Lever' },
  { key: 'ashby', label: 'Ashby' },
  { key: 'linkedin', label: 'LinkedIn' },
  { key: 'naukri', label: 'Naukri' },
  { key: 'indeed', label: 'Indeed' },
  { key: 'glassdoor', label: 'Glassdoor' },
  { key: 'other', label: 'Other portals' },
]

const TIER_STYLE: Record<string, string> = {
  career_page: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  greenhouse: 'bg-teal-500/15 text-teal-300 border-teal-500/30',
  lever: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  ashby: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  linkedin: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  naukri: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  indeed: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
}

interface Filters {
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

const DEFAULT_FILTERS: Filters = {
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

function toParams(f: Filters, page: number): JobSearchParams {
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

function timeAgo(iso: string | null): string {
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

function money(n: number, cur: string): string {
  if (cur === 'INR') return n >= 100_000 ? `₹${+(n / 100_000).toFixed(1)}L` : `₹${Math.round(n).toLocaleString('en-IN')}`
  const sym: Record<string, string> = { USD: '$', EUR: '€', GBP: '£' }
  const s = sym[cur] ?? `${cur} `
  return n >= 1000 ? `${s}${Math.round(n / 1000)}k` : `${s}${Math.round(n)}`
}

function salaryText(j: JobResult): string {
  if (j.salary_min == null && j.salary_max == null) return j.salary_text
  const cur = j.salary_currency || ''
  if (j.salary_min != null && j.salary_max != null && j.salary_min !== j.salary_max)
    return `${money(j.salary_min, cur)} – ${money(j.salary_max, cur)} / yr`
  return `${money((j.salary_max ?? j.salary_min) as number, cur)} / yr`
}

function expText(j: JobResult): string {
  const { experience_min: lo, experience_max: hi } = j
  if (lo == null && hi == null) return ''
  if (lo != null && hi != null) return `${lo}–${hi} yrs exp`
  if (lo != null) return `${lo}+ yrs exp`
  return `up to ${hi} yrs exp`
}

const inputCls =
  'w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600'

function MatchPill({ job }: { job: JobResult }) {
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

function JobCard({ job }: { job: JobResult }) {
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

function ResumePanel({
  profile,
  onChange,
}: {
  profile: CandidateProfile | null
  onChange: (p: CandidateProfile) => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState('')
  const [years, setYears] = useState('')
  const [skills, setSkills] = useState('')

  const upload = async (file: File | undefined) => {
    if (!file) return
    setBusy(true)
    setErr('')
    try {
      onChange(await profileApi.uploadResume(file))
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const startEdit = () => {
    setTitle(profile?.title ?? '')
    setYears(profile?.experience_years != null ? String(profile.experience_years) : '')
    setSkills((profile?.skills ?? []).join(', '))
    setEditing(true)
  }

  const save = async () => {
    setBusy(true)
    setErr('')
    try {
      const y = parseFloat(years)
      onChange(
        await profileApi.update({
          title,
          skills: skills.split(',').map((s) => s.trim()).filter(Boolean),
          experience_years: Number.isFinite(y) ? y : undefined,
        })
      )
      setEditing(false)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-[#111113] border border-zinc-800 rounded-xl p-4 mb-6">
      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.docx,.txt"
        className="hidden"
        onChange={(e) => upload(e.target.files?.[0])}
      />
      {!profile?.has_profile ? (
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div className="text-sm font-medium">See how well you match every job</div>
            <div className="text-xs text-zinc-500 mt-0.5">
              Upload your resume (PDF, DOCX or TXT) to get a match % on each result.
            </div>
          </div>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="bg-white text-black text-sm font-medium px-4 py-2 rounded-md disabled:opacity-50"
          >
            {busy ? 'Reading…' : 'Upload resume'}
          </button>
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="text-sm">
              Matching against <span className="font-medium">{profile.title || 'your resume'}</span>
              <span className="text-zinc-500">
                {profile.experience_years != null ? ` · ${profile.experience_years} yrs` : ''}
                {profile.source_filename ? ` · ${profile.source_filename}` : ''}
              </span>
            </div>
            <div className="flex gap-2">
              <button onClick={startEdit} className="text-xs border border-zinc-700 rounded-md px-3 py-1.5 hover:border-zinc-500">
                Edit
              </button>
              <button
                onClick={() => fileRef.current?.click()}
                disabled={busy}
                className="text-xs border border-zinc-700 rounded-md px-3 py-1.5 hover:border-zinc-500 disabled:opacity-50"
              >
                {busy ? 'Reading…' : 'Update resume'}
              </button>
            </div>
          </div>
          {!editing && profile.skills.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-3">
              {profile.skills.slice(0, 16).map((s) => (
                <span key={s} className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300">
                  {s}
                </span>
              ))}
              {profile.skills.length > 16 && (
                <span className="text-xs text-zinc-500">+{profile.skills.length - 16} more</span>
              )}
            </div>
          )}
          {editing && (
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <input className={inputCls} placeholder="Current role" value={title} onChange={(e) => setTitle(e.target.value)} />
              <input
                className={inputCls}
                placeholder="Years of experience"
                inputMode="decimal"
                value={years}
                onChange={(e) => setYears(e.target.value)}
              />
              <div className="flex gap-2">
                <button onClick={save} disabled={busy} className="bg-white text-black text-sm font-medium px-4 rounded-md disabled:opacity-50">
                  Save
                </button>
                <button onClick={() => setEditing(false)} className="text-sm border border-zinc-700 rounded-md px-3">
                  Cancel
                </button>
              </div>
              <textarea
                className={`${inputCls} sm:col-span-3 h-20`}
                placeholder="Skills, comma separated"
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
              />
            </div>
          )}
        </div>
      )}
      {err && <div className="text-xs text-red-400 mt-2">{err}</div>}
    </div>
  )
}

export default function Jobs() {
  const [hasSearched, setHasSearched] = useState(false)
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [data, setData] = useState<JobSearchResponse | null>(null)
  const [jobs, setJobs] = useState<JobResult[]>([])
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [profile, setProfile] = useState<CandidateProfile | null>(null)
  const [profileLoaded, setProfileLoaded] = useState(false) // first search waits for this, so it runs once
  const [showFilters, setShowFilters] = useState(false)
  const [showSources, setShowSources] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  // Search runs for the committed query; typing alone does not fire a request.
  const [committed, setCommitted] = useState<Filters>(DEFAULT_FILTERS)

  useEffect(() => {
    profileApi
      .get()
      .then(setProfile)
      .catch(() => setProfile(null))
      .finally(() => setProfileLoaded(true))
  }, [])

  const run = useCallback(async (f: Filters, pg: number, append: boolean) => {
    abortRef.current?.abort()
    const ctl = new AbortController()
    abortRef.current = ctl
    setLoading(true)
    setError('')
    try {
      const res = await jobsApi.search(toParams(f, pg), ctl.signal)
      setData(res)
      setJobs((prev) => (append ? [...prev, ...res.results] : res.results))
      setPage(pg)
    } catch (e) {
      if (ctl.signal.aborted) return
      setError(e instanceof Error ? e.message : 'Search failed')
      if (!append) setJobs([])
    } finally {
      if (!ctl.signal.aborted) setLoading(false)
    }
  }, [])

  // Re-run when the committed filters (or the profile, which changes match %) change.
  const profileKey = profile ? `${profile.updated_at}|${profile.skills.join(',')}|${profile.experience_years}|${profile.title}` : 'none'
  useEffect(() => {
    if (!profileLoaded || !hasSearched) return

    run(committed, 1, false)
  }, [committed, profileKey, profileLoaded, hasSearched, run])

  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }))
  const apply = (next?: Partial<Filters>) => {
    setCommitted({ ...filters, ...next })
    setHasSearched(true)
  }
  const hasProfile = !!profile?.has_profile

  const toggleSource = (key: string) => {
    const sources = filters.sources.includes(key) ? filters.sources.filter((s) => s !== key) : [...filters.sources, key]
    setFilters((f) => ({ ...f, sources }))
  }

  const problems = useMemo(() => (data?.sources ?? []).filter((s) => s.status !== 'ok'), [data])
  const activeFilterCount = [
    filters.work_mode,
    filters.salary,
    filters.expMin,
    filters.expMax,
    filters.employment_type,
    filters.posted,
    filters.sources.length ? 'x' : '',
  ].filter(Boolean).length

  return (
    <div className="p-4 sm:p-8 max-w-5xl">
      <h1 className="text-2xl font-semibold mb-1">Search Jobs</h1>
      <p className="text-zinc-400 mb-6">
        Listings from company career pages, Greenhouse, Lever and job portals, newest first within each source.
      </p>

      <ResumePanel profile={profile} onChange={setProfile} />

      <form
        className="grid gap-2 sm:grid-cols-[1fr_220px_auto] mb-3"
        onSubmit={(e) => {
          e.preventDefault()
          apply()
        }}
      >
        <input
          value={filters.q}
          onChange={(e) => set('q', e.target.value)}
          placeholder="Role or keywords, e.g. Backend Engineer"
          className={inputCls}
        />
        <input
          value={filters.location}
          onChange={(e) => set('location', e.target.value)}
          placeholder="Location, e.g. Bengaluru"
          className={inputCls}
        />
        <button type="submit" className="bg-white text-black text-sm font-medium px-5 py-2 rounded-md">
          Search
        </button>
      </form>

      <div className="flex items-center gap-3 mb-4 text-sm">
        <button
          type="button"
          onClick={() => setShowFilters((s) => !s)}
          className="border border-zinc-700 rounded-md px-3 py-1.5 hover:border-zinc-500"
        >
          Filters{activeFilterCount ? ` (${activeFilterCount})` : ''}
        </button>
        <label className="flex items-center gap-2 text-zinc-400">
          Sort
          <select
            value={filters.sort}
            onChange={(e) => {
              set('sort', e.target.value)
              apply({ sort: e.target.value })
            }}
            className="bg-[#111113] border border-zinc-800 rounded-md px-2 py-1.5 text-sm text-white"
          >
            <option value="priority">Source priority, then newest</option>
            <option value="recent">Most recent</option>
            <option value="match" disabled={!hasProfile}>
              Best match{hasProfile ? '' : ' (upload resume)'}
            </option>
          </select>
        </label>
      </div>

      {showFilters && (
        <div className="bg-[#111113] border border-zinc-800 rounded-xl p-4 mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 text-sm">
          <label className="block">
            <span className="block text-zinc-400 mb-1">Work mode</span>
            <select className={inputCls} value={filters.work_mode} onChange={(e) => set('work_mode', e.target.value)}>
              <option value="">Any</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
            </select>
          </label>

          <div>
            <span className="block text-zinc-400 mb-1">
              Min salary ({filters.currency === 'INR' ? 'lakhs per year' : 'thousands per year'})
            </span>
            <div className="flex gap-2">
              <input
                className={inputCls}
                inputMode="decimal"
                placeholder={filters.currency === 'INR' ? 'e.g. 15' : 'e.g. 90'}
                value={filters.salary}
                onChange={(e) => set('salary', e.target.value)}
              />
              <select
                className="bg-[#111113] border border-zinc-800 rounded-md px-2 text-sm text-white"
                value={filters.currency}
                onChange={(e) => set('currency', e.target.value)}
              >
                {['INR', 'USD', 'EUR', 'GBP'].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 mt-2 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={filters.includeNoSalary}
                onChange={(e) => set('includeNoSalary', e.target.checked)}
              />
              Include jobs that don’t list a salary
            </label>
          </div>

          <div>
            <span className="block text-zinc-400 mb-1">Experience required (years)</span>
            <div className="flex items-center gap-2">
              <input className={inputCls} inputMode="decimal" placeholder="Min" value={filters.expMin} onChange={(e) => set('expMin', e.target.value)} />
              <span className="text-zinc-600">–</span>
              <input className={inputCls} inputMode="decimal" placeholder="Max" value={filters.expMax} onChange={(e) => set('expMax', e.target.value)} />
            </div>
            {profile?.experience_years != null && (
              <button
                type="button"
                className="text-xs text-zinc-400 underline mt-1"
                onClick={() => {
                  const y = Math.round(profile.experience_years as number)
                  setFilters((f) => ({ ...f, expMin: String(Math.max(0, y - 1)), expMax: String(y + 2) }))
                }}
              >
                Use my experience ({profile.experience_years} yrs)
              </button>
            )}
          </div>

          <label className="block">
            <span className="block text-zinc-400 mb-1">Job type</span>
            <select
              className={inputCls}
              value={filters.employment_type}
              onChange={(e) => set('employment_type', e.target.value)}
            >
              <option value="">Any</option>
              <option value="full-time">Full-time</option>
              <option value="part-time">Part-time</option>
              <option value="contract">Contract</option>
              <option value="internship">Internship</option>
            </select>
          </label>

          <label className="block">
            <span className="block text-zinc-400 mb-1">Posted</span>
            <select className={inputCls} value={filters.posted} onChange={(e) => set('posted', e.target.value)}>
              <option value="">Any time</option>
              <option value="1">Last 24 hours</option>
              <option value="3">Last 3 days</option>
              <option value="7">Last week</option>
              <option value="14">Last 2 weeks</option>
              <option value="30">Last month</option>
            </select>
          </label>

          <div className="sm:col-span-2 lg:col-span-3">
            <span className="block text-zinc-400 mb-1">Sources</span>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {SOURCES.map((s) => (
                <label key={s.key} className="flex items-center gap-1.5 text-zinc-300">
                  <input type="checkbox" checked={filters.sources.includes(s.key)} onChange={() => toggleSource(s.key)} />
                  {s.label}
                  {data?.facets[s.key] != null && <span className="text-zinc-600">({data.facets[s.key]})</span>}
                </label>
              ))}
              <span className="text-xs text-zinc-600">none selected = all sources</span>
            </div>
          </div>

          <div className="sm:col-span-2 lg:col-span-3 flex gap-2">
            <button type="button" onClick={() => apply()} className="bg-white text-black text-sm font-medium px-4 py-2 rounded-md">
              Apply filters
            </button>
            <button
              type="button"
              onClick={() => {
                const reset = { ...DEFAULT_FILTERS, q: filters.q, location: filters.location }
                setFilters(reset)
                setCommitted(reset)
              }}
              className="text-sm border border-zinc-700 rounded-md px-4 py-2"
            >
              Reset
            </button>
          </div>
        </div>
      )}

      {error && <div className="text-sm text-red-400 mb-3">{error}</div>}

      {data && (
        <div className="flex items-center justify-between text-xs text-zinc-500 mb-3 gap-3 flex-wrap">
          <span>
            {data.total} job{data.total === 1 ? '' : 's'} found
            {!data.profile_used && ' · upload a resume to see match %'}
          </span>
          {problems.length > 0 && (
            <button type="button" className="underline" onClick={() => setShowSources((s) => !s)}>
              {problems.length} source{problems.length === 1 ? '' : 's'} not included
            </button>
          )}
        </div>
      )}

      {showSources && problems.length > 0 && (
        <ul className="text-xs text-zinc-400 bg-[#111113] border border-zinc-800 rounded-lg p-3 mb-4 space-y-1">
          {problems.map((s) => (
            <li key={s.name}>
              <span className="text-zinc-200">{s.name}</span> — {s.status === 'skipped' ? 'not set up: ' : 'failed: '}
              {s.message}
            </li>
          ))}
        </ul>
      )}

      {loading && jobs.length === 0 && <p className="text-sm text-zinc-500">Searching all sources…</p>}

      <div className="space-y-3">
        {jobs.map((j) => (
          <JobCard key={j.id} job={j} />
        ))}
        {!loading && data && jobs.length === 0 && (
          <p className="text-sm text-zinc-500">No jobs match these filters. Try a broader role or fewer filters.</p>
        )}
      </div>

      {data?.has_more && (
        <div className="mt-5">
          <button
            onClick={() => run(committed, page + 1, true)}
            disabled={loading}
            className="border border-zinc-700 rounded-md px-4 py-2 text-sm hover:border-zinc-500 disabled:opacity-50"
          >
            {loading ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  )
}
