import { useEffect, useState } from 'react'
import { prepApi, type ResumeTemplate } from '../lib/api'

const FALLBACK: ResumeTemplate[] = [
  { key: 'ats_classic', label: 'ATS Classic', description: 'Single column, Helvetica, clear section rules. The safest choice for almost every ATS.' },
  { key: 'ats_compact', label: 'ATS Compact', description: 'Same ATS-safe structure with tighter spacing, to fit more on one page.' },
  { key: 'ats_serif', label: 'ATS Serif', description: 'Single column in Times; a traditional look that parses just as cleanly.' },
]

export default function ResumeExport({ sessionId }: { sessionId: number }) {
  const [templates, setTemplates] = useState<ResumeTemplate[]>(FALLBACK)
  const [template, setTemplate] = useState('ats_classic')
  const [page, setPage] = useState('a4')
  const [busy, setBusy] = useState<'pdf' | 'html' | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    prepApi
      .resumeTemplates()
      .then((r) => {
        setTemplates(r.templates)
        setTemplate(r.default)
      })
      .catch(() => {})
  }, [])

  const run = async (kind: 'pdf' | 'html') => {
    setBusy(kind)
    setError('')
    try {
      if (kind === 'pdf') await prepApi.downloadResumePdf(sessionId, template, page)
      else await prepApi.downloadResumeHtml(sessionId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
      <h2 className="font-medium">Export resume</h2>
      <p className="text-xs text-zinc-500 mt-0.5 mb-4">
        Choose a template. All are single-column with real, selectable text and standard headings so applicant
        tracking systems can read them.
      </p>

      <div role="radiogroup" aria-label="Resume template" className="grid gap-3 sm:grid-cols-3">
        {templates.map((t) => {
          const on = template === t.key
          return (
            <button
              key={t.key}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => setTemplate(t.key)}
              className={`text-left rounded-lg border p-3 transition ${
                on ? 'border-white bg-zinc-900' : 'border-zinc-800 hover:border-zinc-600'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{t.label}</span>
                {t.key === 'ats_classic' && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">Recommended</span>
                )}
              </div>
              <p className="text-xs text-zinc-500 mt-1">{t.description}</p>
            </button>
          )
        })}
      </div>

      <div className="flex items-center gap-3 flex-wrap mt-4">
        <button
          type="button"
          onClick={() => run('pdf')}
          disabled={busy !== null}
          className="bg-white text-black text-sm font-medium px-4 py-2 rounded-md hover:bg-zinc-200 disabled:opacity-60"
        >
          {busy === 'pdf' ? 'Preparing PDF…' : 'Download PDF'}
        </button>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          Page size
          <select
            value={page}
            onChange={(e) => setPage(e.target.value)}
            className="bg-[#111113] border border-zinc-800 rounded-md px-2 py-1.5 text-sm text-white"
          >
            <option value="a4">A4</option>
            <option value="letter">US Letter</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => run('html')}
          disabled={busy !== null}
          className="text-sm border border-zinc-700 rounded-md px-3 py-2 hover:border-zinc-500 disabled:opacity-60"
        >
          {busy === 'html' ? 'Preparing…' : 'Download HTML'}
        </button>
      </div>
      {error && <div className="text-xs text-red-400 mt-2">{error}</div>}
    </div>
  )
}
