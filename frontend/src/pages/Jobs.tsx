import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  jobsApi,
  profileApi,
  type CandidateProfile,
  type JobResult,
  type JobSearchResponse,
} from '../lib/api'
import FilterPanel from '../components/jobs/FilterPanel'
import { DEFAULT_FILTERS, JobCard, activeChips, inputCls, toParams, type Filters } from '../components/jobs/shared'

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
  const [refreshing, setRefreshing] = useState(false) // a fresh search (not "Load more") is in flight
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
    setRefreshing(!append)
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
      if (!ctl.signal.aborted) {
        setLoading(false)
        setRefreshing(false)
      }
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

  const problems = useMemo(() => (data?.sources ?? []).filter((s) => s.status !== 'ok'), [data])
  const chips = useMemo(() => activeChips(committed), [committed])
  const activeFilterCount = chips.length
  const removeChip = (clear: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...clear }))
    setCommitted((c) => ({ ...c, ...clear }))
    setHasSearched(true)
  }

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
            {refreshing ? 'Updating results…' : `${data.total} job${data.total === 1 ? '' : 's'} found`}
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

      <div className={`space-y-3 transition-opacity ${refreshing && jobs.length > 0 ? 'opacity-40 pointer-events-none' : ''}`}>
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
