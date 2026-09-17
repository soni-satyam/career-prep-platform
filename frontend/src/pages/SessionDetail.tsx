import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { prepApi } from '../lib/api'
import AtsMatchMeter from '../components/AtsMatchMeter'
import ResumeExport from '../components/ResumeExport'

export default function SessionDetail() {
  const { id } = useParams()
  const [session, setSession] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    prepApi
      .getSession(Number(id))
      .then(setSession)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return <div className="p-8 text-zinc-400">Loading session…</div>
  }
  if (error || !session) {
    return (
      <div className="p-8">
        <p className="text-red-400 mb-4">{error || 'Not found'}</p>
        <Link to="/home" className="text-sm text-zinc-400 hover:text-white">
          ← Back
        </Link>
      </div>
    )
  }

  const plan = session.plan || {}
  const gaps = session.gap_analysis
  const tailored = session.tailored_resume
  const interview = session.interview_pack
  const weeks = plan.preparation_plan || []
  const tips = plan.resume_tips || []

  return (
    <div className="p-8 max-w-4xl space-y-6">
      <div>
        <Link to="/progress" className="text-sm text-zinc-400 hover:text-white">
          ← All sessions
        </Link>
        <h1 className="text-2xl font-semibold mt-2">{session.title}</h1>
        <p className="text-sm text-zinc-500 capitalize mt-1">
          {session.status} · {Math.round(session.progress_pct || 0)}% complete
        </p>
      </div>

      {plan.ats_match && <AtsMatchMeter match={plan.ats_match} />}
      {tailored && <ResumeExport sessionId={session.id} />}

      {gaps && (
        <section className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
          <h2 className="font-medium mb-3">Gap analysis</h2>
          <div className="text-xs text-zinc-500 mb-2">
            Readiness: <span className="text-zinc-300">{gaps.overall_readiness}</span>
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
              <div className="text-zinc-300">{g.description}</div>
              {g.how_to_close && <div className="text-xs text-zinc-500">{g.how_to_close}</div>}
            </div>
          ))}
        </section>
      )}

      {weeks.length > 0 && (
        <section className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
          <h2 className="font-medium mb-3">Preparation plan</h2>
          <div className="space-y-4">
            {weeks.map((w: any) => (
              <div key={w.week}>
                <div className="text-sm font-medium text-white">
                  Week {w.week}: {w.focus}
                </div>
                <ul className="mt-1 text-sm text-zinc-400 list-disc list-inside">
                  {(w.tasks || []).map((t: string, i: number) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      {tailored && (
        <section className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
          <h2 className="font-medium mb-3">Tailored resume</h2>
          {tailored.summary && <p className="text-sm text-zinc-300 mb-3">{tailored.summary}</p>}
          {tailored.skills?.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {tailored.skills.map((s: string, i: number) => (
                <span key={i} className="text-xs bg-zinc-800 px-2 py-1 rounded">
                  {s}
                </span>
              ))}
            </div>
          )}
          {tailored.experience?.map((e: any) => (
            <div key={e.id} className="mb-3">
              <div className="text-sm font-medium">{e.title}</div>
              <div className="text-sm text-zinc-400 whitespace-pre-wrap">{e.content}</div>
            </div>
          ))}
        </section>
      )}

      {interview?.interview_qa?.length > 0 && (
        <section className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
          <h2 className="font-medium mb-3">Interview Q&A</h2>
          <div className="space-y-3">
            {interview.interview_qa.slice(0, 6).map((q: any, i: number) => (
              <div key={q.id || i}>
                <div className="text-sm font-medium text-white">{q.question}</div>
                <div className="text-sm text-zinc-400 mt-1">{q.answer}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {tips.length > 0 && (
        <section className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
          <h2 className="font-medium mb-2">Resume tips</h2>
          <ul className="text-sm text-zinc-300 list-disc list-inside">
            {tips.map((t: string, i: number) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
