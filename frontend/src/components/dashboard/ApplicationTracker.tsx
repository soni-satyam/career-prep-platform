import { forwardRef, useCallback, useEffect, useImperativeHandle, useState } from 'react'
import { ChevronDown, ChevronUp, ExternalLink, Plus, Trash2 } from 'lucide-react'
import {
  STATUSES,
  trackerApi,
  type Application,
  type ApplicationStatus,
  type DashboardData,
} from '../../lib/dashboardApi'
import { card, dayDelta, inputCls, shortDate, STATUS_STYLE } from './format'

export interface TrackerHandle {
  openAdd: () => void
  reload: () => void
}

type Tab = 'all' | ApplicationStatus

const ApplicationTracker = forwardRef<
  TrackerHandle,
  { counts: DashboardData['stats']['by_status']; onChanged: () => void }
>(function ApplicationTracker({ counts, onChanged }, ref) {
  const [tab, setTab] = useState<Tab>('all')
  const [apps, setApps] = useState<Application[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState(false)
  const [openId, setOpenId] = useState<number | null>(null)

  const load = useCallback(async (t: Tab) => {
    setError('')
    try {
      setApps(await trackerApi.listApplications(t === 'all' ? undefined : t))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load applications')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(tab)
  }, [tab, load])

  useImperativeHandle(ref, () => ({ openAdd: () => setAdding(true), reload: () => load(tab) }), [load, tab])

  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const tabs: Array<{ key: Tab; label: string; n: number }> = [
    { key: 'all', label: 'All', n: total },
    ...STATUSES.map((s) => ({ key: s.key as Tab, label: s.label, n: counts[s.key] ?? 0 })),
  ]

  const mutate = async (fn: () => Promise<unknown>) => {
    setError('')
    try {
      await fn()
      await load(tab)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    }
  }

  return (
    <div className={card}>
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h2 className="font-medium">Application tracker</h2>
        <button
          onClick={() => setAdding((a) => !a)}
          className="inline-flex items-center gap-1.5 text-xs border border-zinc-700 rounded-md px-3 py-1.5 hover:border-zinc-500"
        >
          <Plus size={14} /> Add application
        </button>
      </div>

      <div className="flex gap-1.5 flex-wrap mb-4" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => {
              setLoading(true)
              setTab(t.key)
            }}
            className={`text-xs rounded-full px-3 py-1 border transition ${
              tab === t.key ? 'bg-white text-black border-white' : 'border-zinc-700 text-zinc-400 hover:border-zinc-500'
            }`}
          >
            {t.label} <span className={tab === t.key ? 'text-zinc-600' : 'text-zinc-600'}>{t.n}</span>
          </button>
        ))}
      </div>

      {adding && (
        <AddForm
          onCancel={() => setAdding(false)}
          onSubmit={(body) =>
            mutate(async () => {
              await trackerApi.addApplication(body)
              setAdding(false)
            })
          }
        />
      )}

      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {loading && <p className="text-sm text-zinc-500">Loading…</p>}
      {!loading && apps.length === 0 && (
        <p className="text-sm text-zinc-500">
          {tab === 'all'
            ? 'Nothing tracked yet. Add an application, or press “I applied” on any job.'
            : 'No applications in this stage.'}
        </p>
      )}

      <ul className="space-y-2">
        {apps.map((a) => (
          <li key={a.id} className="rounded-lg bg-zinc-900/50 border border-zinc-800/80">
            <div className="flex items-center gap-3 p-3 flex-wrap sm:flex-nowrap">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium truncate">{a.title}</span>
                  {a.url && (
                    <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-zinc-500 hover:text-white shrink-0" aria-label="Open job posting">
                      <ExternalLink size={13} />
                    </a>
                  )}
                </div>
                <div className="text-xs text-zinc-500 truncate">
                  {[a.company, a.source_label, a.applied_on ? `applied ${shortDate(a.applied_on)}` : ''].filter(Boolean).join(' · ')}
                </div>
                {a.next_step && (
                  <div className="text-xs text-amber-300/90 mt-0.5 truncate">
                    Next: {a.next_step}
                    {a.next_step_date ? ` (${dayDelta(a.next_step_date)})` : ''}
                  </div>
                )}
              </div>
              <select
                value={a.status}
                onChange={(e) => mutate(() => trackerApi.updateApplication(a.id, { status: e.target.value as ApplicationStatus }))}
                className={`text-xs rounded-md border px-2 py-1.5 bg-transparent ${STATUS_STYLE[a.status]}`}
                aria-label={`Status for ${a.title}`}
              >
                {STATUSES.map((s) => (
                  <option key={s.key} value={s.key} className="bg-zinc-900 text-white">
                    {s.label}
                  </option>
                ))}
              </select>
              <button
                onClick={() => setOpenId(openId === a.id ? null : a.id)}
                className="text-zinc-500 hover:text-white"
                aria-label="Details"
                aria-expanded={openId === a.id}
              >
                {openId === a.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
            </div>
            {openId === a.id && (
              <Details
                app={a}
                onSave={(patch) => mutate(() => trackerApi.updateApplication(a.id, patch))}
                onDelete={() => {
                  if (window.confirm(`Remove “${a.title}” from your tracker?`)) mutate(() => trackerApi.deleteApplication(a.id))
                }}
              />
            )}
          </li>
        ))}
      </ul>
    </div>
  )
})

export default ApplicationTracker

function AddForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (b: { title: string; company: string; url: string; status: ApplicationStatus; applied_on?: string }) => void
  onCancel: () => void
}) {
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [url, setUrl] = useState('')
  const [status, setStatus] = useState<ApplicationStatus>('applied')
  const [date, setDate] = useState('')
  return (
    <form
      className="grid gap-2 sm:grid-cols-2 mb-4 p-3 rounded-lg border border-zinc-800 bg-zinc-900/40"
      onSubmit={(e) => {
        e.preventDefault()
        if (title.trim()) onSubmit({ title: title.trim(), company: company.trim(), url: url.trim(), status, applied_on: date || undefined })
      }}
    >
      <input className={inputCls} placeholder="Job title *" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus required />
      <input className={inputCls} placeholder="Company" value={company} onChange={(e) => setCompany(e.target.value)} />
      <input className={inputCls} placeholder="Link to the posting (optional)" value={url} onChange={(e) => setUrl(e.target.value)} />
      <div className="flex gap-2">
        <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value as ApplicationStatus)}>
          {STATUSES.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <input className={inputCls} type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Applied on" />
      </div>
      <div className="sm:col-span-2 flex gap-2">
        <button type="submit" className="bg-white text-black text-sm font-medium px-4 py-1.5 rounded-md">
          Add
        </button>
        <button type="button" onClick={onCancel} className="text-sm border border-zinc-700 rounded-md px-3 py-1.5">
          Cancel
        </button>
      </div>
    </form>
  )
}

function Details({
  app,
  onSave,
  onDelete,
}: {
  app: Application
  onSave: (p: { next_step: string; next_step_date?: string; clear_next_step_date?: boolean; notes: string }) => void
  onDelete: () => void
}) {
  const [step, setStep] = useState(app.next_step)
  const [date, setDate] = useState(app.next_step_date ?? '')
  const [notes, setNotes] = useState(app.notes)
  return (
    <div className="px-3 pb-3 grid gap-2 sm:grid-cols-2 border-t border-zinc-800/80 pt-3">
      <input className={inputCls} placeholder="Next step, e.g. Technical round" value={step} onChange={(e) => setStep(e.target.value)} />
      <input className={inputCls} type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Next step date" />
      <textarea className={`${inputCls} sm:col-span-2 h-16`} placeholder="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className="sm:col-span-2 flex items-center justify-between">
        <button
          onClick={() => onSave({ next_step: step, notes, ...(date ? { next_step_date: date } : { clear_next_step_date: true }) })}
          className="bg-white text-black text-xs font-medium px-3 py-1.5 rounded-md"
        >
          Save
        </button>
        <button onClick={onDelete} className="inline-flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300">
          <Trash2 size={13} /> Remove
        </button>
      </div>
    </div>
  )
}
