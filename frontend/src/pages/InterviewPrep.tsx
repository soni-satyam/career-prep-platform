import { useState } from 'react'
import { prepApi } from '../lib/api'

export default function InterviewPrep() {
  const [resumeText, setResumeText] = useState('')
  const [jdText, setJdText] = useState('')
  const [role, setRole] = useState('')
  const [company, setCompany] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pack, setPack] = useState<any>(null)

  const run = async () => {
    if (!jdText.trim()) {
      setError('Please paste a job description.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const session = await prepApi.createSession({
        jd_text: jdText,
        resume_text: resumeText || undefined,
        target_role: role || undefined,
        company: company || undefined,
        mode: 'interview',
      })
      setPack(session.interview_pack || session.plan)
    } catch (e: any) {
      setError(e.message || 'Failed to generate interview pack')
    } finally {
      setLoading(false)
    }
  }

  const qa = pack?.interview_qa || []
  const focus = pack?.focus_areas || []

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-2xl font-semibold mb-1">Interview Preparation</h1>
      <p className="text-zinc-400 mb-8">
        Get AI-generated questions and sample answers based on the job and your background.
        {' '}
        <a href="/live-interview" className="text-white underline">Try live AI interview →</a>
      </p>

      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
          {error}
        </div>
      )}

      {!pack && (
        <div className="space-y-4 max-w-2xl">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-zinc-400 mb-1.5">Job role</label>
              <input
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="Software Engineer"
                className="w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
              />
            </div>
            <div>
              <label className="block text-sm text-zinc-400 mb-1.5">Company (optional)</label>
              <input
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="Google"
                className="w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">Job description</label>
            <textarea
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              rows={8}
              placeholder="Paste the JD..."
              className="w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
            />
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">Your resume (optional but recommended)</label>
            <textarea
              value={resumeText}
              onChange={(e) => setResumeText(e.target.value)}
              rows={6}
              placeholder="Paste resume text for better answers..."
              className="w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
            />
          </div>
          <button
            onClick={run}
            disabled={loading}
            className="bg-white text-black font-medium px-6 py-2.5 rounded-md hover:bg-zinc-200 transition disabled:opacity-60"
          >
            {loading ? 'Generating questions…' : 'Generate Questions →'}
          </button>
        </div>
      )}

      {pack && (
        <div className="space-y-6">
          <button onClick={() => setPack(null)} className="text-sm text-zinc-400 hover:text-white">
            ← Generate new set
          </button>

          {focus.length > 0 && (
            <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
              <h2 className="font-medium mb-2">Focus areas</h2>
              <div className="flex flex-wrap gap-2">
                {focus.map((f: string, i: number) => (
                  <span key={i} className="text-xs bg-amber-500/15 text-amber-400 px-2.5 py-1 rounded">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-4">
            {qa.map((item: any, idx: number) => (
              <div key={item.id || idx} className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] uppercase tracking-wide text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded">
                    {item.category || 'general'}
                  </span>
                  <span className="text-xs text-zinc-600">#{idx + 1}</span>
                </div>
                <div className="text-sm font-medium text-white mb-2">{item.question}</div>
                <div className="text-sm text-zinc-400 whitespace-pre-wrap leading-relaxed">
                  {item.answer}
                </div>
                {item.tips && (
                  <div className="mt-2 text-xs text-emerald-400/80">Tip: {item.tips}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
