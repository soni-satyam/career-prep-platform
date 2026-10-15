import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Building2, FileText, HelpCircle, MessageSquare, Mic, Plus, Search, Upload } from 'lucide-react'
import { profileApi } from '../../lib/api'
import { useFeatures } from '../../lib/features'

const links = [
  { to: '/jobs', label: 'Search jobs', icon: Search, flag: 'job_search' },
  { to: '/resume', label: 'Tailor resume', icon: FileText, flag: 'resume_tailor' },
  { to: '/interview', label: 'Interview prep', icon: MessageSquare, flag: 'interview_prep' },
  { to: '/live-interview', label: 'AI interview', icon: Mic, flag: 'interview_prep' },
  { to: '/companies', label: 'Companies', icon: Building2, flag: 'company_search' },
  { to: '/quizzes', label: 'Quizzes', icon: HelpCircle, flag: 'quizzes' },
]

export default function QuickActions({
  hasResume,
  onResumeUploaded,
  onAddApplication,
}: {
  hasResume: boolean
  onResumeUploaded: () => void
  onAddApplication: () => void
}) {
  const { enabled } = useFeatures()
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const upload = async (file?: File) => {
    if (!file) return
    setBusy(true)
    setErr('')
    try {
      await profileApi.uploadResume(file)
      onResumeUploaded()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const primary = 'inline-flex items-center gap-2 text-sm font-medium px-3.5 py-2 rounded-md transition'
  const secondary =
    'inline-flex items-center gap-2 text-sm text-zinc-300 border border-zinc-800 bg-[#111113] px-3.5 py-2 rounded-md hover:border-zinc-600 hover:text-white transition'

  return (
    <div>
      <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className={`${primary} ${hasResume ? 'border border-zinc-700 text-zinc-200 hover:border-zinc-500' : 'bg-white text-black hover:bg-zinc-200'} disabled:opacity-60`}
        >
          <Upload size={15} />
          {busy ? 'Reading…' : hasResume ? 'Update resume' : 'Upload resume'}
        </button>
        <button onClick={onAddApplication} className={`${primary} border border-zinc-700 text-zinc-200 hover:border-zinc-500`}>
          <Plus size={15} />
          Add application
        </button>
        {links
          .filter((l) => enabled(l.flag))
          .map(({ to, label, icon: Icon }) => (
            <Link key={to} to={to} className={secondary}>
              <Icon size={15} strokeWidth={1.75} />
              {label}
            </Link>
          ))}
      </div>
      {err && <div className="text-xs text-red-400 mt-2">{err}</div>}
    </div>
  )
}
