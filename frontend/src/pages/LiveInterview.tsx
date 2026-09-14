import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

type Phase = 'setup' | 'interview' | 'report'

interface Question {
  question_id: string
  category: string
  question: string
  is_follow_up?: boolean
}

interface HistoryItem {
  question_id: string
  question: string
  category: string
  answer?: string
  score?: number
  feedback?: string
}

export default function LiveInterview() {
  const [phase, setPhase] = useState<Phase>('setup')
  const [role, setRole] = useState('Software Engineer')
  const [difficulty, setDifficulty] = useState('medium')
  const [duration, setDuration] = useState(15)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [interviewId, setInterviewId] = useState('')
  const [maxQuestions, setMaxQuestions] = useState(6)
  const [currentQ, setCurrentQ] = useState<Question | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [questionsAsked, setQuestionsAsked] = useState(0)
  const [answerText, setAnswerText] = useState('')
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [lastFeedback, setLastFeedback] = useState<string | null>(null)
  const [report, setReport] = useState<any>(null)
  const [sessionId, setSessionId] = useState<number | null>(null)

  const recognitionRef = useRef<any>(null)

  const speak = useCallback((text: string) => {
    if (!window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text)
    u.rate = 1
    u.pitch = 1
    u.onstart = () => setSpeaking(true)
    u.onend = () => setSpeaking(false)
    u.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(u)
  }, [])

  useEffect(() => {
    return () => {
      window.speechSynthesis?.cancel()
      recognitionRef.current?.stop?.()
    }
  }, [])

  const startListening = () => {
    const SR =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) {
      setError('Speech recognition is not supported in this browser. Type your answer instead.')
      return
    }
    const rec = new SR()
    recognitionRef.current = rec
    rec.continuous = true
    rec.interimResults = true
    rec.lang = 'en-US'
    rec.onresult = (event: any) => {
      let final = ''
      for (let i = 0; i < event.results.length; i++) {
        final += event.results[i][0].transcript
      }
      setAnswerText(final.trim())
    }
    rec.onerror = () => setListening(false)
    rec.onend = () => setListening(false)
    rec.start()
    setListening(true)
  }

  const stopListening = () => {
    recognitionRef.current?.stop?.()
    setListening(false)
  }

  const startInterview = async () => {
    setError(null)
    setLoading(true)
    try {
      const data = await api<any>('/api/v1/live-interview/start', {
        method: 'POST',
        body: JSON.stringify({
          role,
          difficulty,
          duration_minutes: duration,
        }),
      })
      setInterviewId(data.interview_id)
      setMaxQuestions(data.max_questions)
      setCurrentQ(data.question)
      setHistory([])
      setQuestionsAsked(1)
      setLastFeedback(null)
      setReport(null)
      setPhase('interview')
      speak(data.question.question)
    } catch (e: any) {
      setError(e.message || 'Failed to start interview')
    } finally {
      setLoading(false)
    }
  }

  const submitAnswer = async () => {
    if (!currentQ || !answerText.trim()) {
      setError('Please answer before continuing (speak or type).')
      return
    }
    stopListening()
    window.speechSynthesis?.cancel()
    setError(null)
    setLoading(true)
    try {
      const data = await api<any>('/api/v1/live-interview/answer', {
        method: 'POST',
        body: JSON.stringify({
          interview_id: interviewId,
          question_id: currentQ.question_id,
          question: currentQ.question,
          category: currentQ.category,
          answer: answerText.trim(),
          history,
          questions_asked: questionsAsked,
          role,
          difficulty,
          max_questions: maxQuestions,
        }),
      })

      const eval_ = data.evaluation || {}
      const updatedHistory: HistoryItem[] = [
        ...history,
        {
          question_id: currentQ.question_id,
          question: currentQ.question,
          category: currentQ.category,
          answer: answerText.trim(),
          score: eval_.score,
          feedback: eval_.feedback,
        },
      ]
      setHistory(updatedHistory)
      setLastFeedback(eval_.feedback || null)
      setAnswerText('')

      if (data.done || !data.next_question) {
        // finish
        const fin = await api<any>('/api/v1/live-interview/finish', {
          method: 'POST',
          body: JSON.stringify({
            interview_id: interviewId,
            role,
            difficulty,
            history: updatedHistory,
            save_session: true,
          }),
        })
        setReport(fin.report)
        setSessionId(fin.session_id)
        setPhase('report')
      } else {
        const nq = data.next_question
        setCurrentQ({
          question_id: nq.question_id || `q${questionsAsked + 1}`,
          category: nq.category || 'technical',
          question: nq.question,
          is_follow_up: nq.is_follow_up,
        })
        setQuestionsAsked((n) => n + 1)
        speak(nq.question)
      }
    } catch (e: any) {
      setError(e.message || 'Failed to evaluate answer')
    } finally {
      setLoading(false)
    }
  }

  const endEarly = async () => {
    stopListening()
    window.speechSynthesis?.cancel()
    setLoading(true)
    try {
      const hist = [...history]
      if (currentQ && answerText.trim()) {
        hist.push({
          question_id: currentQ.question_id,
          question: currentQ.question,
          category: currentQ.category,
          answer: answerText.trim(),
        })
      }
      const fin = await api<any>('/api/v1/live-interview/finish', {
        method: 'POST',
        body: JSON.stringify({
          interview_id: interviewId || 'early',
          role,
          difficulty,
          history: hist,
          save_session: true,
        }),
      })
      setHistory(hist)
      setReport(fin.report)
      setSessionId(fin.session_id)
      setPhase('report')
    } catch (e: any) {
      setError(e.message || 'Failed to finish')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1">AI Live Interview</h1>
      <p className="text-zinc-400 mb-8">
        Speak with the AI interviewer — questions are read aloud, answers via mic or typing.
      </p>

      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
          {error}
        </div>
      )}

      {phase === 'setup' && (
        <div className="bg-[#111113] border border-zinc-800 rounded-xl p-6 space-y-4 max-w-lg">
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">Role</label>
            <input
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full bg-[#0a0a0b] border border-zinc-700 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-500"
            />
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">Difficulty</label>
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value)}
              className="w-full bg-[#0a0a0b] border border-zinc-700 rounded-md px-3 py-2 text-sm text-white"
            >
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">Duration (minutes)</label>
            <select
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full bg-[#0a0a0b] border border-zinc-700 rounded-md px-3 py-2 text-sm text-white"
            >
              {[10, 15, 20, 30, 45].map((m) => (
                <option key={m} value={m}>
                  {m} min
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={startInterview}
            disabled={loading}
            className="w-full bg-white text-black font-medium py-2.5 rounded-md hover:bg-zinc-200 disabled:opacity-60"
          >
            {loading ? 'Starting…' : 'Start interview'}
          </button>
          <p className="text-xs text-zinc-600">
            Uses browser speech synthesis (TTS) and speech recognition (mic). Chrome works best.
          </p>
        </div>
      )}

      {phase === 'interview' && currentQ && (
        <div className="space-y-5">
          <div className="flex items-center justify-between text-xs text-zinc-500">
            <span>
              Question {questionsAsked} / {maxQuestions}
              {currentQ.is_follow_up ? ' · Follow-up' : ''}
            </span>
            <span className="capitalize">{currentQ.category}</span>
          </div>

          <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
            <div className="flex items-start justify-between gap-3">
              <p className="text-lg text-white leading-relaxed">{currentQ.question}</p>
              <button
                type="button"
                onClick={() => speak(currentQ.question)}
                disabled={speaking}
                className="shrink-0 text-xs border border-zinc-700 rounded-md px-2 py-1 text-zinc-300 hover:border-zinc-500"
              >
                {speaking ? 'Speaking…' : 'Replay'}
              </button>
            </div>
          </div>

          {lastFeedback && (
            <div className="text-sm text-zinc-400 border-l-2 border-emerald-500/40 pl-3">
              Previous feedback: {lastFeedback}
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-zinc-400">Your answer</label>
              <div className="flex gap-2">
                {!listening ? (
                  <button
                    type="button"
                    onClick={startListening}
                    className="text-xs bg-rose-500/20 text-rose-300 border border-rose-500/30 px-2.5 py-1 rounded-md"
                  >
                    🎤 Start mic
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={stopListening}
                    className="text-xs bg-rose-500 text-white px-2.5 py-1 rounded-md animate-pulse"
                  >
                    Stop mic
                  </button>
                )}
              </div>
            </div>
            <textarea
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              rows={5}
              placeholder="Speak or type your answer…"
              className="w-full bg-[#111113] border border-zinc-800 rounded-xl px-4 py-3 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
            />
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={submitAnswer}
              disabled={loading}
              className="bg-white text-black font-medium px-5 py-2.5 rounded-md hover:bg-zinc-200 disabled:opacity-60"
            >
              {loading ? 'Evaluating…' : 'Submit answer'}
            </button>
            <button
              onClick={endEarly}
              disabled={loading}
              className="border border-zinc-700 text-zinc-300 px-4 py-2.5 rounded-md text-sm hover:border-zinc-500"
            >
              End & get report
            </button>
          </div>
        </div>
      )}

      {phase === 'report' && report && (
        <div className="space-y-6">
          <div className="bg-[#111113] border border-zinc-800 rounded-xl p-6">
            <div className="flex items-end gap-4 mb-4">
              <div>
                <div className="text-4xl font-semibold">{report.overall_score ?? '—'}</div>
                <div className="text-xs text-zinc-500">Overall / 10</div>
              </div>
              <p className="text-sm text-zinc-300 flex-1">{report.summary}</p>
            </div>
            {report.category_scores && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                {Object.entries(report.category_scores).map(([k, v]) => (
                  <div key={k} className="bg-zinc-900/80 rounded-lg p-3">
                    <div className="text-lg font-medium">{String(v)}</div>
                    <div className="text-[11px] text-zinc-500 capitalize">{k.replace('_', ' ')}</div>
                  </div>
                ))}
              </div>
            )}
            {report.strengths?.length > 0 && (
              <div className="mb-3">
                <div className="text-sm font-medium mb-1">Strengths</div>
                <ul className="text-sm text-zinc-400 list-disc list-inside">
                  {report.strengths.map((s: string, i: number) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {report.improvements?.length > 0 && (
              <div className="mb-3">
                <div className="text-sm font-medium mb-1">Improvements</div>
                <ul className="text-sm text-zinc-400 list-disc list-inside">
                  {report.improvements.map((s: string, i: number) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {report.recommended_practice?.length > 0 && (
              <div>
                <div className="text-sm font-medium mb-1">Recommended practice</div>
                <ul className="text-sm text-zinc-400 list-disc list-inside">
                  {report.recommended_practice.map((s: string, i: number) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => {
                setPhase('setup')
                setReport(null)
                setHistory([])
                setCurrentQ(null)
              }}
              className="bg-white text-black font-medium px-4 py-2 rounded-md text-sm"
            >
              New interview
            </button>
            {sessionId && (
              <Link
                to={`/sessions/${sessionId}`}
                className="border border-zinc-700 text-zinc-300 px-4 py-2 rounded-md text-sm hover:border-zinc-500"
              >
                View saved session
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
