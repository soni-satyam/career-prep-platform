import { useEffect, useRef, useState } from 'react'
import { companiesApi, jobsApi, type CompanyProfile, type FeaturedCompany } from '../lib/api'
import CompanyJobs from '../components/company/CompanyJobs'
import { inputCls } from '../components/jobs/shared'

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div className="text-xs text-zinc-500 mb-0.5">{label}</div>
      <div className={`text-sm ${value ? 'text-zinc-100' : 'text-zinc-600'}`}>{value || 'Not found online'}</div>
    </div>
  )
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

// Companies the person has opened before, kept in this browser so they are one click away next time.
interface Recent {
  name: string
  website: string
}
const RECENT_KEY = 'careerprep.recentCompanies'

function loadRecent(): Recent[] {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
    return Array.isArray(v) ? v.filter((r) => r && typeof r.name === 'string').slice(0, 8) : []
  } catch {
    return []
  }
}

function saveRecent(list: Recent[]) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  } catch {
    /* storage unavailable (private mode, quota): the list just won't persist */
  }
}

export default function Companies() {
  const [q, setQ] = useState('')
  const [company, setCompany] = useState<CompanyProfile | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showJobs, setShowJobs] = useState(false)
  const [featured, setFeatured] = useState<FeaturedCompany[]>([])
  const [recent, setRecent] = useState<Recent[]>(loadRecent)
  const [opening, setOpening] = useState('')        // name of the card/chip being opened right now
  const abortRef = useRef<AbortController | null>(null)
  const jobsRef = useRef<HTMLDivElement | null>(null)
  const profileRef = useRef<HTMLDivElement | null>(null)

  // the platform's own list of companies; if it can't load, the page still works through search
  useEffect(() => {
    jobsApi
      .companies()
      .then((list: FeaturedCompany[]) => setFeatured(list))
      .catch(() => setFeatured([]))
  }, [])

  const remember = (c: CompanyProfile) =>
    setRecent((prev) => {
      const next = [{ name: c.name, website: c.website }, ...prev.filter((r) => r.name.toLowerCase() !== c.name.toLowerCase())].slice(0, 8)
      saveRecent(next)
      return next
    })

  const lookup = async (query: string, website?: string) => {
    const text = query.trim()
    if (text.length < 2) return
    abortRef.current?.abort()
    const ctl = new AbortController()
    abortRef.current = ctl
    setLoading(true)
    setOpening(text)
    setError('')
    setShowJobs(false)
    try {
      const found = await companiesApi.lookup(text, website, ctl.signal)
      setCompany(found)
      setQ('')
      remember(found)
    } catch (e) {
      if (ctl.signal.aborted) return
      setCompany(null)
      setError(e instanceof Error ? e.message : 'Could not look up this company')
    } finally {
      if (!ctl.signal.aborted) {
        setLoading(false)
        setOpening('')
      }
    }
  }

  useEffect(() => () => abortRef.current?.abort(), [])

  // show the profile as soon as it is ready (the cards sit below the fold on small screens)
  useEffect(() => {
    if (company) profileRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [company])

  // bring the job list into view once the person asks for it
  useEffect(() => {
    if (showJobs) jobsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [showJobs])

  return (
    <div className="p-4 sm:p-8 max-w-4xl">
      <h1 className="text-2xl font-semibold mb-1">Company Search</h1>
      <p className="text-zinc-400 mb-6">
        Look up any company, from large employers to early-stage startups, and see its open jobs.
      </p>

      <form
        className="flex gap-2 mb-2"
        onSubmit={(e) => {
          e.preventDefault()
          lookup(q)
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Company name or website, e.g. Stripe or acme.io"
          className={inputCls}
          autoFocus
        />
        <button
          type="submit"
          disabled={loading || q.trim().length < 2}
          className="bg-white text-black text-sm font-medium px-5 py-2 rounded-md disabled:opacity-50 shrink-0"
        >
          {loading ? 'Looking up…' : 'Search'}
        </button>
      </form>
      <p className="text-xs text-zinc-500 mb-6">
        Can’t find a small company by name? Search with its website address instead.
      </p>

      {recent.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-6">
          <span className="text-xs text-zinc-500">Recent:</span>
          {recent.map((r) => (
            <button
              key={r.name}
              type="button"
              disabled={loading}
              onClick={() => lookup(r.name, r.website || undefined)}
              className="text-xs border border-zinc-700 rounded-full px-3 py-1 text-zinc-300 hover:border-zinc-500 disabled:opacity-50"
            >
              {r.name}
            </button>
          ))}
          <button
            type="button"
            className="text-xs text-zinc-600 hover:text-zinc-400 underline"
            onClick={() => {
              setRecent([])
              saveRecent([])
            }}
          >
            Clear
          </button>
        </div>
      )}

      {loading && (
        <p className="text-sm text-zinc-500 mb-4">
          {opening ? `Opening ${opening}… ` : ''}Finding the company and reading its website.
        </p>
      )}
      {error && <div className="text-sm text-red-400 mb-4">{error}</div>}

      {!company && featured.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-zinc-300 mb-3">Popular companies</h2>
          <div className="grid sm:grid-cols-2 gap-3">
            {featured.map((c) => (
              <button
                key={c.id}
                type="button"
                disabled={loading}
                onClick={() => lookup(c.name, c.website || undefined)}
                className="text-left bg-[#111113] border border-zinc-800 rounded-xl p-4 hover:border-zinc-500 transition disabled:opacity-60 focus:outline-none focus:border-zinc-500"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-sm">{c.name}</span>
                  <span className="text-xs text-zinc-500">{opening === c.name ? 'Opening…' : 'View details →'}</span>
                </div>
                {c.description && <p className="text-xs text-zinc-500 mt-1">{c.description}</p>}
                {c.tech_stack && c.tech_stack.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {c.tech_stack.map((t) => (
                      <span key={t} className="text-[10px] bg-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </div>
        </section>
      )}

      {company && !loading && (
        <div ref={profileRef}>
          <button
            type="button"
            onClick={() => {
              setCompany(null)
              setShowJobs(false)
            }}
            className="text-xs text-zinc-400 hover:text-white mb-3"
          >
            ← Popular companies
          </button>
          <article className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
            <div className="flex items-start gap-4">
              {company.logo && (
                <img
                  src={company.logo}
                  alt=""
                  className="w-12 h-12 rounded-lg object-contain bg-white p-1 shrink-0"
                  referrerPolicy="no-referrer"
                  onError={(e) => (e.currentTarget.style.display = 'none')}
                />
              )}
              <div className="min-w-0">
                <h2 className="text-xl font-semibold">{company.name}</h2>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  {company.website && (
                    <a
                      href={company.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-zinc-400 hover:text-white underline"
                    >
                      {domainOf(company.website)} ↗
                    </a>
                  )}
                  {company.linkedin_url && (
                    <a
                      href={company.linkedin_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-zinc-400 hover:text-white underline"
                    >
                      LinkedIn ↗
                    </a>
                  )}
                </div>
              </div>
            </div>

            {company.confidence !== 'high' && company.website && (
              <div className="text-xs rounded-md border border-amber-500/30 bg-amber-500/10 text-amber-200 px-3 py-2 mt-4">
                We matched this to {domainOf(company.website)}. Check that it’s the company you meant.
              </div>
            )}

            <p className="text-sm text-zinc-200 mt-4 leading-relaxed">
              {company.summary || 'We couldn’t find a description of this company online.'}
            </p>
            {company.what_it_does && company.what_it_does !== company.summary && (
              <p className="text-sm text-zinc-400 mt-2">
                <span className="text-zinc-500">What it does: </span>
                {company.what_it_does}
              </p>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5">
              <Fact label="Founded" value={company.founded} />
              <Fact label="Headquarters" value={company.headquarters} />
              <Fact label="Industry" value={company.industry} />
              <Fact label="Company size" value={company.size} />
            </div>

            <div className="mt-5">
              <div className="text-xs text-zinc-500 mb-1">Career page</div>
              {company.career_url ? (
                <a
                  href={company.career_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-emerald-300 hover:underline break-all"
                >
                  {company.career_url} ↗
                </a>
              ) : (
                <span className="text-sm text-zinc-500">
                  No career page found. We’ll still search job boards and the web.
                </span>
              )}
              {company.career_status === 'guessed' && (
                <span className="text-xs text-zinc-500 ml-2">(guessed from the website)</span>
              )}
            </div>

            {company.links.length > 0 && (
              <div className="mt-5">
                <div className="text-xs text-zinc-500 mb-1.5">Browse jobs elsewhere</div>
                <div className="flex flex-wrap gap-2">
                  {company.links.map((l) => (
                    <a
                      key={l.label}
                      href={l.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs border border-zinc-700 rounded-full px-3 py-1 text-zinc-300 hover:border-zinc-500"
                    >
                      {l.label} ↗
                    </a>
                  ))}
                </div>
              </div>
            )}

            {company.notes.length > 0 && (
              <ul className="mt-4 text-xs text-zinc-500 space-y-1">
                {company.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}

            {company.alternatives.length > 0 && (
              <div className="mt-5 text-xs text-zinc-500">
                Not the right company? Try:{' '}
                {company.alternatives.map((a, i) => (
                  <span key={a.website}>
                    {i > 0 && ', '}
                    <button
                      type="button"
                      className="underline text-zinc-300 hover:text-white"
                      onClick={() => lookup(company.name, a.website)}
                    >
                      {a.name || a.domain} ({a.domain})
                    </button>
                  </span>
                ))}
              </div>
            )}

            {company.sources.length > 0 && (
              <div className="mt-4 text-xs text-zinc-600 break-all">
                Sources: {company.sources.map(domainOf).join(' · ')}
              </div>
            )}

            <div className="mt-6 pt-5 border-t border-zinc-800">
              <button
                type="button"
                onClick={() => setShowJobs(true)}
                disabled={showJobs}
                className="bg-white text-black text-sm font-medium px-5 py-2.5 rounded-md disabled:opacity-60"
              >
                {showJobs ? `Showing jobs at ${company.name}` : `Get jobs at ${company.name}`}
              </button>
            </div>
          </article>
        </div>
      )}

      {company && showJobs && (
        <div ref={jobsRef}>
          <CompanyJobs key={`${company.name}|${company.website}`} company={company} />
        </div>
      )}
    </div>
  )
}
