import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { profileApi } from '../../lib/api'
import type { ResumeStatus } from '../../lib/dashboardApi'
import { card, timeAgo } from './format'

export default function ResumeStatusCard({ resume, onChanged }: { resume: ResumeStatus; onChanged: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const upload = async (file?: File) => {
    if (!file) return
    setBusy(true)
    setErr('')
    try {
      await profileApi.uploadResume(file)
      onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const pct = resume.completeness
  const tone = !resume.uploaded ? '#52525b' : pct >= 80 ? '#34d399' : pct >= 55 ? '#fbbf24' : '#f87171'

  return (
    <div className={card}>
      <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-medium">Resume</h2>
        {resume.uploaded && resume.stale && (
          <span className="text-xs px-2 py-0.5 rounded bg-amber-500/15 text-amber-300">Out of date</span>
        )}
        {resume.uploaded && !resume.stale && (
          <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300">Active</span>
        )}
      </div>

      {!resume.uploaded ? (
        <div>
          <p className="text-sm text-zinc-400 mb-4">
            No resume yet. Upload one to see a match % on every job and get personalised recommendations.
          </p>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="bg-white text-black text-sm font-medium px-4 py-2 rounded-md hover:bg-zinc-200 disabled:opacity-60"
          >
            {busy ? 'Reading…' : 'Upload resume'}
          </button>
          <div className="text-xs text-zinc-600 mt-2">PDF, DOCX or TXT</div>
        </div>
      ) : (
        <div>
          <div className="flex items-center gap-4">
            <div className="relative h-16 w-16 shrink-0">
              <svg className="h-16 w-16 -rotate-90" viewBox="0 0 36 36" role="img" aria-label={`Profile ${pct}% complete`}>
                <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#27272a" strokeWidth="3" />
                <circle cx="18" cy="18" r="15.9155" fill="none" stroke={tone} strokeWidth="3" strokeLinecap="round" strokeDasharray={`${pct}, 100`} />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-sm font-medium">{pct}%</span>
            </div>
            <div className="min-w-0 text-sm">
              <div className="font-medium truncate">{resume.title || 'Role not set'}</div>
              <div className="text-xs text-zinc-500 truncate">{resume.filename}</div>
              <div className="text-xs text-zinc-500 mt-0.5">
                {resume.skills_count} skills
                {resume.experience_years != null ? ` · ${resume.experience_years} yrs` : ''}
                {resume.updated_at ? ` · updated ${timeAgo(resume.updated_at)}` : ''}
              </div>
            </div>
          </div>

          {resume.next_steps.length > 0 && (
            <ul className="mt-4 space-y-1.5 text-xs text-zinc-400">
              {resume.next_steps.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-amber-400">•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="flex gap-2 mt-4">
            <button
              onClick={() => fileRef.current?.click()}
              disabled={busy}
              className="text-xs border border-zinc-700 rounded-md px-3 py-1.5 hover:border-zinc-500 disabled:opacity-60"
            >
              {busy ? 'Reading…' : 'Update resume'}
            </button>
            <Link to="/jobs" className="text-xs border border-zinc-700 rounded-md px-3 py-1.5 hover:border-zinc-500">
              Edit skills
            </Link>
          </div>
        </div>
      )}
      {err && <div className="text-xs text-red-400 mt-2">{err}</div>}
    </div>
  )
}
