import { SOURCES, inputCls, type Filters } from './shared'

interface Props {
  filters: Filters
  setFilters: (update: (f: Filters) => Filters) => void
  facets?: Record<string, number>
  experienceYears?: number | null
  /** limit the "Sources" checkboxes (defaults to all) */
  sources?: Array<{ key: string; label: string }>
  onApply: () => void
  onReset: () => void
}

export default function FilterPanel({ filters, setFilters, facets, experienceYears, sources = SOURCES, onApply, onReset }: Props) {
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }))
  const toggleSource = (key: string) =>
    setFilters((f) => ({
      ...f,
      sources: f.sources.includes(key) ? f.sources.filter((s) => s !== key) : [...f.sources, key],
    }))

  return (
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
        {experienceYears != null && (
          <button
            type="button"
            className="text-xs text-zinc-400 underline mt-1"
            onClick={() => {
              const y = Math.round(experienceYears as number)
              setFilters((f) => ({ ...f, expMin: String(Math.max(0, y - 1)), expMax: String(y + 2) }))
            }}
          >
            Use my experience ({experienceYears} yrs)
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
          {sources.map((s) => (
            <label key={s.key} className="flex items-center gap-1.5 text-zinc-300">
              <input type="checkbox" checked={filters.sources.includes(s.key)} onChange={() => toggleSource(s.key)} />
              {s.label}
              {facets?.[s.key] != null && <span className="text-zinc-600">({facets[s.key]})</span>}
            </label>
          ))}
          <span className="text-xs text-zinc-600">none selected = all sources</span>
        </div>
      </div>

      <div className="sm:col-span-2 lg:col-span-3 flex gap-2">
        <button
          type="button"
          onClick={onApply}
          className="bg-white text-black text-sm font-medium px-4 py-2 rounded-md"
        >
          Apply filters
        </button>
        <button
          type="button"
          onClick={onReset}
          className="text-sm border border-zinc-700 rounded-md px-4 py-2"
        >
          Reset
        </button>
      </div>
    </div>
  )
}
