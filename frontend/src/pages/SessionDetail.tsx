import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { prepApi } from '../lib/api'
import ReadinessPanel from '../components/ReadinessPanel'
import ResumeWorkspace from '../components/ResumeWorkspace'

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
    <div className="p-4 sm:p-8 max-w-7xl space-y-6">
      <div>
        <Link to="/progress" className="text-sm text-zinc-400 hover:text-white">
          ← All sessions
        </Link>
        <h1 className="text-2xl font-semibold mt-2">{session.title}</h1>
        <p className="text-sm text-zinc-500 capitalize mt-1">
          {session.status} · {Math.round(session.progress_pct || 0)}% complete
        </p>
      </div>

      {tailored ? (
        // match meters, readiness, editor + live preview, approve & download
        <ResumeWorkspace key={session.id} session={session} tips={tips} />
      ) : (
        gaps && <ReadinessPanel readiness={plan.readiness ?? null} analysis={gaps} />
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

      {!tailored && tips.length > 0 && (
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
