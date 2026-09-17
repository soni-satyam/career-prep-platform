import { useState } from 'react'
import { Link } from 'react-router-dom'
import { prepApi } from '../lib/api'
import ResumeWorkspace from '../components/ResumeWorkspace'

export default function ResumeTailor() {
  const [resumeText, setResumeText] = useState('')
  const [jdText, setJdText] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)
  const [step, setStep] = useState<'input' | 'result'>('input')
  const [statusMsg, setStatusMsg] = useState('')
  const [uploadingJd, setUploadingJd] = useState(false)
  const [resumeFile, setResumeFile] = useState('')
  const [jdFile, setJdFile] = useState('')

  const onFile = async (file: File | null) => {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const res = await prepApi.extractText(file)
      setResumeText(res.text)
      setResumeFile(file.name)
    } catch (e: any) {
      setError(e.message || 'Failed to read file')
    } finally {
      setUploading(false)
    }
  }

  const onJdFile = async (file: File | null) => {
    if (!file) return
    setUploadingJd(true)
    setError(null)
    try {
      const res = await prepApi.extractText(file)
      setJdText(res.text)
      setJdFile(file.name)
    } catch (e: any) {
      setError(e.message || 'Failed to read file')
    } finally {
      setUploadingJd(false)
    }
  }

  const run = async () => {
    if (!resumeText.trim() || !jdText.trim()) {
      setError('Please provide both your resume and a job description.')
      return
    }
    setError(null)
    setLoading(true)
    setStatusMsg('Reading both documents, analyzing the job, comparing it with your experience and writing your tailored resume… this can take a minute.')
    try {
      const session = await prepApi.createSession({
        jd_text: jdText,
        resume_text: resumeText,
        mode: 'resume',
      })
      setResult(session)
      setStep('result')
    } catch (e: any) {
      setError(e.message || 'Failed to generate tailored resume')
    } finally {
      setLoading(false)
      setStatusMsg('')
    }
  }

  const tailored = result?.tailored_resume
  const tips = result?.plan?.resume_tips || []

  return (
    <div className="p-4 sm:p-8 max-w-6xl">
      <h1 className="text-2xl font-semibold mb-1">Tailor Your Resume</h1>
      <p className="text-zinc-400 mb-8">
        Upload or paste your resume and a job description to get a tailored version, gap analysis, and tips.
      </p>

      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
          {error}
        </div>
      )}

      {step === 'input' && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm text-zinc-400 mb-2">1. Your resume</label>
            <div className="mb-2">
              <label className="inline-flex items-center gap-2 text-xs text-zinc-400 border border-zinc-700 rounded-md px-3 py-1.5 cursor-pointer hover:border-zinc-500">
                {uploading ? 'Extracting…' : 'Upload resume (PDF / DOCX / TXT)'}
                <input
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf"
                  className="hidden"
                  disabled={uploading}
                  onChange={(e) => onFile(e.target.files?.[0] || null)}
                />
              </label>
              {resumeFile && <span className="text-xs text-zinc-500 ml-3">{resumeFile} · {resumeText.length.toLocaleString()} characters read</span>}
            </div>
            <textarea
              value={resumeText}
              onChange={(e) => setResumeText(e.target.value)}
              placeholder="Paste your resume text here, or upload a file…"
              rows={14}
              className="w-full bg-[#111113] border border-zinc-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 resize-y"
            />
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-2">2. Job description</label>
            <div className="mb-2">
              <label className="inline-flex items-center gap-2 text-xs text-zinc-400 border border-zinc-700 rounded-md px-3 py-1.5 cursor-pointer hover:border-zinc-500">
                {uploadingJd ? 'Extracting…' : 'Upload job description (PDF / DOCX / TXT)'}
                <input
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf"
                  className="hidden"
                  disabled={uploadingJd}
                  onChange={(e) => onJdFile(e.target.files?.[0] || null)}
                />
              </label>
              {jdFile && <span className="text-xs text-zinc-500 ml-3">{jdFile} · {jdText.length.toLocaleString()} characters read</span>}
            </div>
            <textarea
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder="Paste the job description here..."
              rows={14}
              className="w-full bg-[#111113] border border-zinc-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 resize-y"
            />
          </div>
          <div className="lg:col-span-2">
            <button
              onClick={run}
              disabled={loading}
              className="bg-white text-black font-medium px-6 py-2.5 rounded-md hover:bg-zinc-200 transition disabled:opacity-60"
            >
              {loading ? 'Generating…' : 'Generate tailored resume →'}
            </button>
            {statusMsg && <p className="text-xs text-zinc-500 mt-2">{statusMsg}</p>}
          </div>
        </div>
      )}

      {step === 'result' && result && (
        <div className="space-y-6">
          <div className="flex items-center gap-4">
            <button onClick={() => setStep('input')} className="text-sm text-zinc-400 hover:text-white">
              ← Back to editor
            </button>
            <Link to={`/sessions/${result.id}`} className="text-sm text-zinc-400 hover:text-white">
              Open full session →
            </Link>
          </div>

          {tailored && <ResumeWorkspace key={result.id} session={result} />}

          {tips.length > 0 && (
            <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
              <h2 className="font-medium mb-3">Resume tips</h2>
              <ul className="space-y-2 text-sm text-zinc-300 list-disc list-inside">
                {tips.map((t: string, i: number) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
