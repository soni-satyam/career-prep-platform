import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  companiesApi,
  profileApi,
  type CandidateProfile,
  type CompanyJobsResponse,
  type CompanyProfile,
  type JobResult,
} from '../../lib/api'
import FilterPanel from '../jobs/FilterPanel'
import { DEFAULT_FILTERS, JobCard, activeChips, inputCls, toParams, type Filters } from '../jobs/shared'

type CareerInfo = CompanyJobsResponse['career_page']

// What happened when we tried to read the company's own career page, in plain words.
function careerBanner(company: CompanyProfile, info: CareerInfo): { tone: 'good' | 'warn'; text: string; url: string } | null {
  if (!info) {
    return {
      tone: 'warn',
      text: "We couldn't find this company's career page, so these results come from job boards and web search.",
      url: '',
    }
  }
  const good = info.status === 'ok' || info.status === 'boards_only'
  return { tone: good ? 'good' : 'warn', text: info.note, url: info.url || company.career_url }
}

export default function CompanyJobs({ company }: { company: CompanyProfile }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [committed, setCommitted] = useState<Filters>(DEFAULT_FILTERS)
  const [data, setData] = useState<CompanyJobsResponse | null>(null)
  const [jobs, setJobs] = useState<JobResult[]>([])
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(true)
  const [error, setError] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [showSources, setShowSources] = useState(false)
  const [profile, setProfile] = useState<CandidateProfile | null>(null)
  const [profileLoaded, setProfileLoaded] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    profileApi
      .get()
      .then(setProfile)
      .catch(() => setProfile(null))
      .finally(() => setProfileLoaded(true))
  }, [])

  const run = useCallback(
    async (f: Filters, pg: number, append: boolean) => {
      abortRef.current?.abort()
      const ctl = new AbortController()
      abortRef.current = ctl
      setLoading(true)
      setRefreshing(!append)
      setError('')
      try {
        const res = await companiesApi.jobs(company.name, company.website, toParams(f, pg), ctl.signal)
        setData(res)
        setJobs((prev) => (append ? [...prev, ...res.results] : res.results))
        setPage(pg)
      } catch (e) {
        if (ctl.signal.aborted) return
        setError(e instanceof Error ? e.message : 'Could not load jobs')
        if (!append) setJobs([])
      } finally {
        if (!ctl.signal.aborted) {
          setLoading(false)
          setRefreshing(false)
        }
      }
    },
    [company.name, company.website],
  )

  const profileKey = profile ? `${profile.updated_at}|${profile.skills.join(',')}|${profile.experience_years}` : 'none'
  useEffect(() => {
    if (!profileLoaded) return
    run(committed, 1, false)
    return () => abortRef.current?.abort()
  }, [committed, profileKey, profileLoaded, run])

  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }))
  const apply = (next?: Partial<Filters>) => setCommitted({ ...filters, ...next })
  const removeChip = (clear: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...clear }))
    setCommitted((c) => ({ ...c, ...clear }))
  }

  const chips = useMemo(() => activeChips(committed), [committed])
  const problems = useMemo(() => (data?.sources ?? []).filter((s) => s.status !== 'ok'), [data])
  const banner = data ? careerBanner(company, data.career_page) : null
  const hasProfile = !!profile?.has_profile

  return (
    <section className="mt-8 pt-6 border-t border-zinc-800">
      <h2 className="text-lg font-semibold mb-1">Jobs at {company.name}</h2>
      <p className="text-sm text-zinc-400 mb-4">
        From the company’s own career page and job boards, plus job sites found through web search.
      </p>

      {banner && (
        <div
          className={`text-sm rounded-lg border px-3 py-2 mb-4 ${
            banner.tone === 'good'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-200'
              : 'bg-amber-500/10 border-amber-500/30 text-amber-200'
          }`}
        >
          {banner.text}
          {banner.url && (
            <>
              {' '}
              <a href={banner.url} target="_blank" rel="noopener noreferrer" className="underline">
                Open career page ↗
              </a>
            </>
          )}
        </div>
      )}

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
          placeholder={`Role or keywords at ${company.name}`}
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
          Filters{chips.length ? ` (${chips.length})` : ''}
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
        <FilterPanel
          filters={filters}
          setFilters={setFilters}
          facets={data?.facets}
          experienceYears={profile?.experience_years}
          onApply={() => {
            apply()
            setShowFilters(false)
          }}
          onReset={() => {
            const reset = { ...DEFAULT_FILTERS, q: filters.q, location: filters.location }
            setFilters(reset)
            setCommitted(reset)
          }}
        />
      )}

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-3">
          {chips.map((c) => (
            <span
              key={c.key}
              className="inline-flex items-center gap-1.5 text-xs bg-zinc-800 border border-zinc-700 rounded-full pl-2.5 pr-1.5 py-1 text-zinc-200"
            >
              {c.label}
              <button
                type="button"
                aria-label={`Remove filter ${c.label}`}
                onClick={() => removeChip(c.clear)}
                className="text-zinc-400 hover:text-white leading-none px-1"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {error && <div className="text-sm text-red-400 mb-3">{error}</div>}

      {data && (
        <div className="flex items-center justify-between text-xs text-zinc-500 mb-3 gap-3 flex-wrap">
          <span>
            {refreshing ? 'Updating results…' : `${data.total} job${data.total === 1 ? '' : 's'} at ${company.name}`}
            {!data.profile_used && ' · upload a resume on the Jobs page to see match %'}
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

      {loading && jobs.length === 0 && (
        <p className="text-sm text-zinc-500">
          Reading {company.name}’s career page and searching job sites… this can take a few seconds.
        </p>
      )}

      <div className={`space-y-3 transition-opacity ${refreshing && jobs.length > 0 ? 'opacity-40 pointer-events-none' : ''}`}>
        {jobs.map((j) => (
          <JobCard key={j.id} job={j} />
        ))}
        {!loading && data && jobs.length === 0 && (
          <div className="text-sm text-zinc-500">
            {chips.length || committed.q || committed.location
              ? 'No jobs match these filters. Try fewer filters or a broader keyword.'
              : `No open jobs found for ${company.name} right now. Try the links under “Browse jobs elsewhere” above.`}
          </div>
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
    </section>
  )
}
