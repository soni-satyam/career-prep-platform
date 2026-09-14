import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { jobsApi } from '../lib/api'

export default function Jobs() {
  const [jobs, setJobs] = useState<any[]>([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)

  const load = (query?: string) => {
    setLoading(true)
    jobsApi
      .list(query)
      .then(setJobs)
      .catch(() => setJobs([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-2xl font-semibold mb-1">Search Jobs</h1>
      <p className="text-zinc-400 mb-6">Browse sample openings (seed data for demo).</p>

      <form
        className="flex gap-2 mb-6"
        onSubmit={(e) => {
          e.preventDefault()
          load(q)
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. Software Engineer, Bangalore"
          className="flex-1 bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
        />
        <button type="submit" className="bg-white text-black text-sm font-medium px-4 py-2 rounded-md">
          Search
        </button>
      </form>

      {loading && <p className="text-sm text-zinc-500">Loading…</p>}
      <div className="space-y-3">
        {jobs.map((j) => (
          <Link
            key={j.id}
            to={`/jobs/${j.id}`}
            className="block bg-[#111113] border border-zinc-800 rounded-xl p-4 hover:border-zinc-600 transition"
          >
            <div className="font-medium text-sm">{j.title}</div>
            <div className="text-xs text-zinc-500 mt-1">
              {j.company?.name || 'Company'} · {j.location || '—'} · {j.seniority || ''} ·{' '}
              {j.employment_type || ''}
            </div>
            {j.description && (
              <p className="text-sm text-zinc-400 mt-2 line-clamp-2">{j.description}</p>
            )}
          </Link>
        ))}
        {!loading && jobs.length === 0 && (
          <p className="text-sm text-zinc-500">No jobs found.</p>
        )}
      </div>
    </div>
  )
}
