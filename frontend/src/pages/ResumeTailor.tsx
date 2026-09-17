import { useState } from 'react'
import { Link } from 'react-router-dom'
import { prepApi, type AtsMatch } from '../lib/api'
import AtsMatchMeter from '../components/AtsMatchMeter'
import ResumeExport from '../components/ResumeExport'

export default function ResumeTailor() {
  const [resumeText, setResumeText] = useState('')
  const [jdText, setJdText] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)
  const [step, setStep] = useState<'input' | 'result'>('input')
  const [statusMsg, setStatusMsg] = useState('')

  const onFile = async (file: File | null) => {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const res = await prepApi.extractText(file)
      setResumeText(res.text)
    } catch (e: any) {
      setError(e.message || 'Failed to read file')
    } finally {
      setUploading(false)
    }
  }

  const run = async () => {
    if (!resumeText.trim() || !jdText.trim()) {
      setError('Please provide both your resume and a job description.')
      return
    }
    setError(null)
    setLoading(true)
    setStatusMsg('Running multi-agent pipeline (JD → profile → gaps → resume → tips)…')
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
  const gaps = result?.gap_analysis
  const tips = result?.plan?.resume_tips || []
  const atsMatch: AtsMatch | null = result?.plan?.ats_match ?? null

  return (
    <div className="p-8 max-w-5xl">
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
                {uploading ? 'Extracting…' : 'Upload PDF / DOCX / TXT'}
                <input
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf"
                  className="hidden"
                  disabled={uploading}
                  onChange={(e) => onFile(e.target.files?.[0] || null)}
                />
              </label>
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
            <textarea
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder="Paste the job description here..."
              rows={16}
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

          {atsMatch && <AtsMatchMeter match={atsMatch} />}

          {tailored && <ResumeExport sessionId={result.id} />}

          {gaps && (
            <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
              <div className="flex items-center gap-3 mb-3">
                <span className="text-sm font-medium">Overall readiness</span>
                <span className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">
                  {gaps.overall_readiness}
                </span>
              </div>
              {gaps.strengths?.length > 0 && (
                <ul className="text-sm text-zinc-300 list-disc list-inside mb-3">
                  {gaps.strengths.map((s: string, i: number) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              )}
              {gaps.gaps?.map((g: any) => (
                <div key={g.id} className="text-sm border-l-2 border-amber-500/50 pl-3 mb-2">
                  <span className="text-zinc-300">{g.description}</span>
                  {g.how_to_close && (
                    <div className="text-xs text-zinc-500 mt-0.5">{g.how_to_close}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {tailored && (
            <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
              <h2 className="font-medium mb-4">Tailored Resume</h2>
              {tailored.summary && (
                <p className="text-sm text-zinc-300 mb-4 leading-relaxed">{tailored.summary}</p>
              )}
              {tailored.skills?.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {tailored.skills.map((s: string, i: number) => (
                    <span key={i} className="text-xs bg-zinc-800 text-zinc-300 px-2 py-1 rounded">
                      {s}
                    </span>
                  ))}
                </div>
              )}
              {tailored.experience?.map((exp: any) => (
                <div key={exp.id} className="mb-4">
                  <div className="text-sm font-medium text-white">{exp.title}</div>
                  <div className="text-sm text-zinc-400 whitespace-pre-wrap mt-1">{exp.content}</div>
                </div>
              ))}
              {tailored.projects?.map((p: any) => (
                <div key={p.id} className="mb-4">
                  <div className="text-sm font-medium text-white">{p.title}</div>
                  <div className="text-sm text-zinc-400 whitespace-pre-wrap mt-1">{p.content}</div>
                </div>
              ))}
            </div>
          )}

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
