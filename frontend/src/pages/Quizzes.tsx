import { useState } from 'react'
import { api } from '../lib/api'
import { splitCodeFences } from '../lib/quizText'

interface Q {
  id: string
  category?: string
  question: string
  options: string[]
  correct_index: number
  explanation: string
}

interface QuizResponse {
  questions: Q[]
  topic: string
  difficulty?: string
  question_type?: string
  num_requested?: number
}

// Keep in sync with QUESTION_TYPES in backend/app/agents/quiz_agent.py
const QUESTION_TYPES = [
  { id: 'mixed', label: 'Mix-up', desc: 'Concepts, scenarios, code reading and tricky questions blended.' },
  { id: 'interview', label: 'Interview style', desc: 'What interviewers actually ask: why, when and trade-offs.' },
  { id: 'assessment', label: 'Assessment style', desc: 'Online-test / screening round: crisp, timed, one clear answer.' },
  { id: 'most_asked', label: 'Most asked', desc: 'Classic, high-frequency questions on the topic.' },
  { id: 'conceptual', label: 'Conceptual', desc: 'Fundamentals and how things work under the hood.' },
  { id: 'practical', label: 'Practical', desc: 'Real-world scenarios, debugging and design choices.' },
  { id: 'coding', label: 'Code & output', desc: 'Read code, predict the output, spot the bug.' },
] as const

const COUNTS = [5, 10, 15, 20]

function QuestionText({ text }: { text: string }) {
  return (
    <div className="space-y-2">
      {splitCodeFences(text).map((part, i) =>
        part.code ? (
          <pre
            key={i}
            className="text-xs bg-black/40 border border-zinc-800 rounded-md p-3 overflow-x-auto font-mono text-zinc-200 whitespace-pre"
          >
            {part.text}
          </pre>
        ) : (
          <p key={i} className="whitespace-pre-wrap">
            {part.text}
          </p>
        ),
      )}
    </div>
  )
}

export default function Quizzes() {
  const [topic, setTopic] = useState('Data Structures')
  const [difficulty, setDifficulty] = useState('medium')
  const [numQuestions, setNumQuestions] = useState(5)
  const [questionType, setQuestionType] = useState<string>('mixed')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [questions, setQuestions] = useState<Q[]>([])
  const [meta, setMeta] = useState<{ type: string; difficulty: string; requested: number } | null>(null)
  const [answers, setAnswers] = useState<Record<number, number>>({})
  const [submitted, setSubmitted] = useState(false)

  const typeInfo = QUESTION_TYPES.find((t) => t.id === questionType) || QUESTION_TYPES[0]

  const generate = async () => {
    if (loading) return // ignore double clicks: every request is an LLM call
    if (topic.trim().length < 2) {
      setError('Please enter a topic.')
      return
    }
    setLoading(true)
    setError(null)
    setSubmitted(false)
    setAnswers({})
    try {
      const data = await api<QuizResponse>('/api/v1/quizzes/generate', {
        method: 'POST',
        body: JSON.stringify({
          topic: topic.trim(),
          difficulty,
          num_questions: numQuestions,
          question_type: questionType,
        }),
      })
      setQuestions(data.questions || [])
      setMeta({
        type: data.question_type || questionType,
        difficulty: data.difficulty || difficulty,
        requested: data.num_requested || numQuestions,
      })
    } catch (e: any) {
      setError(e.message || 'Failed to generate quiz')
    } finally {
      setLoading(false)
    }
  }

  const score = questions.reduce((acc, q, i) => {
    return acc + (answers[i] === q.correct_index ? 1 : 0)
  }, 0)
  const answered = Object.keys(answers).length
  const metaLabel = QUESTION_TYPES.find((t) => t.id === meta?.type)?.label

  return (
    <div className="p-8 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1">Practice Quizzes</h1>
      <p className="text-zinc-400 mb-8">Sharpen skills with AI-generated multiple-choice quizzes.</p>

      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-[#111113] border border-zinc-800 rounded-xl p-5 mb-6 space-y-5">
        <div className="flex flex-wrap gap-3">
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Topic e.g. System Design, Python, SQL"
            aria-label="Topic"
            className="flex-1 min-w-[200px] bg-[#0b0b0c] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-600"
          />
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            aria-label="Difficulty"
            className="bg-[#0b0b0c] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white"
          >
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </div>

        <div>
          <div className="text-xs text-zinc-400 mb-2">Number of questions</div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Number of questions">
            {COUNTS.map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={numQuestions === n}
                onClick={() => setNumQuestions(n)}
                className={`px-4 py-1.5 rounded-md text-sm border transition ${
                  numQuestions === n
                    ? 'border-white bg-white text-black font-medium'
                    : 'border-zinc-800 text-zinc-300 hover:border-zinc-600'
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="text-xs text-zinc-400 mb-2">Type of questions</div>
          <div className="grid sm:grid-cols-2 gap-2" role="group" aria-label="Type of questions">
            {QUESTION_TYPES.map((t) => (
              <button
                key={t.id}
                type="button"
                aria-pressed={questionType === t.id}
                onClick={() => setQuestionType(t.id)}
                className={`text-left px-3 py-2.5 rounded-md border transition ${
                  questionType === t.id
                    ? 'border-blue-500/70 bg-blue-500/10'
                    : 'border-zinc-800 hover:border-zinc-600'
                }`}
              >
                <div className="text-sm font-medium text-white">{t.label}</div>
                <div className="text-xs text-zinc-400 mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>
          {questionType === 'most_asked' && (
            <p className="text-xs text-zinc-500 mt-2">
              Based on commonly asked patterns the AI knows, not live interview data.
            </p>
          )}
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={generate}
            disabled={loading}
            className="bg-white text-black font-medium px-5 py-2 rounded-md text-sm hover:bg-zinc-200 disabled:opacity-60"
          >
            {loading ? 'Generating…' : `Generate ${numQuestions} questions`}
          </button>
          <span className="text-xs text-zinc-500">
            {loading
              ? numQuestions > 10
                ? 'Larger quizzes can take 20–30 seconds…'
                : 'This usually takes a few seconds…'
              : `${typeInfo.label} · ${difficulty}`}
          </span>
        </div>
      </div>

      {questions.length > 0 && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
            <span>
              {questions.length} questions · {metaLabel} · {meta?.difficulty}
            </span>
            {meta && questions.length < meta.requested && (
              <span className="text-amber-400">
                The AI returned {questions.length} of {meta.requested} requested. Use “New quiz” for a fresh set.
              </span>
            )}
          </div>

          {questions.map((q, qi) => (
            <div key={q.id || qi} className="bg-[#111113] border border-zinc-800 rounded-xl p-5">
              {q.category && (
                <span className="inline-block text-[11px] uppercase tracking-wide text-zinc-400 bg-zinc-800 rounded px-2 py-0.5 mb-2">
                  {q.category}
                </span>
              )}
              <div className="text-sm font-medium mb-3 flex gap-1.5">
                <span>{qi + 1}.</span>
                <div className="min-w-0 flex-1">
                  <QuestionText text={q.question} />
                </div>
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
                <p className="mt-3 text-xs text-zinc-400 whitespace-pre-wrap">{q.explanation}</p>
              )}
            </div>
          ))}

          {!submitted ? (
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSubmitted(true)}
                className="bg-white text-black font-medium px-5 py-2 rounded-md text-sm"
              >
                Submit answers
              </button>
              <span className="text-xs text-zinc-500">
                {answered} of {questions.length} answered
              </span>
            </div>
          ) : (
            <div className="text-sm text-zinc-300">
              Score: <span className="text-white font-semibold">{score}</span> / {questions.length}
              <span className="text-zinc-500"> ({Math.round((score / questions.length) * 100)}%)</span>
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
