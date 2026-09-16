import { useState } from 'react'
import { api } from '../lib/api'

interface Q {
  id: string
  question: string
  options: string[]
  correct_index: number
  explanation: string
}

export default function Quizzes() {
  const [topic, setTopic] = useState('Data Structures')
  const [difficulty, setDifficulty] = useState('medium')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [questions, setQuestions] = useState<Q[]>([])
  const [answers, setAnswers] = useState<Record<number, number>>({})
  const [submitted, setSubmitted] = useState(false)

  const generate = async () => {
    if (loading) return // ignore double clicks: every request is an LLM call
    setLoading(true)
    setError(null)
    setSubmitted(false)
    setAnswers({})
    try {
      const data = await api<{ questions: Q[]; topic: string }>('/api/v1/quizzes/generate', {
        method: 'POST',
        body: JSON.stringify({ topic, difficulty, num_questions: 5 }),
      })
      setQuestions(data.questions || [])
    } catch (e: any) {
      setError(e.message || 'Failed to generate quiz')
    } finally {
      setLoading(false)
    }
  }

  const score = questions.reduce((acc, q, i) => {
    return acc + (answers[i] === q.correct_index ? 1 : 0)
  }, 0)

  return (
    <div className="p-8 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1">Practice Quizzes</h1>
      <p className="text-zinc-400 mb-8">Sharpen skills with AI-generated multiple-choice quizzes.</p>

      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="flex flex-wrap gap-3 mb-6">
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="Topic e.g. System Design, Python, SQL"
          className="flex-1 min-w-[200px] bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-600"
        />
        <select
          value={difficulty}
          onChange={(e) => setDifficulty(e.target.value)}
          className="bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white"
        >
          <option value="easy">Easy</option>
          <option value="medium">Medium</option>
          <option value="hard">Hard</option>
        </select>
        <button
          onClick={generate}
          disabled={loading}
          className="bg-white text-black font-medium px-4 py-2 rounded-md text-sm hover:bg-zinc-200 disabled:opacity-60"
        >
          {loading ? 'Generating…' : 'Generate quiz'}
        </button>
      </div>

      {questions.length > 0 && (
        <div className="space-y-5">
          {questions.map((q, qi) => (
            <div key={q.id || qi} className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
              <div className="text-sm font-medium mb-3">
                {qi + 1}. {q.question}
              </div>
              <div className="space-y-2">
                {(q.options || []).map((opt, oi) => {
                  const selected = answers[qi] === oi
                  let cls = 'border-zinc-800 hover:border-zinc-600'
                  if (submitted) {
                    if (oi === q.correct_index) cls = 'border-emerald-500/60 bg-emerald-500/10'
                    else if (selected) cls = 'border-red-500/60 bg-red-500/10'
                  } else if (selected) {
                    cls = 'border-blue-500/60 bg-blue-500/10'
                  }
                  return (
                    <button
                      key={oi}
                      type="button"
                      disabled={submitted}
                      onClick={() => setAnswers((a) => ({ ...a, [qi]: oi }))}
                      className={`w-full text-left text-sm px-3 py-2 rounded-md border transition ${cls}`}
                    >
                      {opt}
                    </button>
                  )
                })}
              </div>
              {submitted && q.explanation && (
                <p className="mt-3 text-xs text-zinc-400">{q.explanation}</p>
              )}
            </div>
          ))}

          {!submitted ? (
            <button
              onClick={() => setSubmitted(true)}
              className="bg-white text-black font-medium px-5 py-2 rounded-md text-sm"
            >
              Submit answers
            </button>
          ) : (
            <div className="text-sm text-zinc-300">
              Score: <span className="text-white font-semibold">{score}</span> / {questions.length}
              <button
                onClick={generate}
                disabled={loading}
                className="ml-4 text-zinc-400 hover:text-white underline disabled:opacity-50"
              >
                {loading ? 'Generating…' : 'New quiz'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
