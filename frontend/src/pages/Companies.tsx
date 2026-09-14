import { useEffect, useState } from 'react'
import { jobsApi } from '../lib/api'

export default function Companies() {
  const [companies, setCompanies] = useState<any[]>([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)

  const load = (query?: string) => {
    setLoading(true)
    jobsApi
      .companies(query)
      .then(setCompanies)
      .catch(() => setCompanies([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-2xl font-semibold mb-1">Search Companies</h1>
      <p className="text-zinc-400 mb-6">Explore companies, tech stacks and culture signals.</p>

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
          placeholder="e.g. Google, Microsoft"
          className="flex-1 bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
        />
        <button type="submit" className="bg-white text-black text-sm font-medium px-4 py-2 rounded-md">
          Search
        </button>
      </form>

      {loading && <p className="text-sm text-zinc-500">Loading…</p>}
      <div className="grid sm:grid-cols-2 gap-3">
        {companies.map((c) => (
          <div
            key={c.id}
            className="bg-[#111113] border border-zinc-800 rounded-xl p-4 hover:border-zinc-600 transition"
          >
            <div className="font-medium text-sm">{c.name}</div>
            <p className="text-xs text-zinc-500 mt-1">{c.description}</p>
            {c.tech_stack?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {c.tech_stack.map((t: string) => (
                  <span key={t} className="text-[10px] bg-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
