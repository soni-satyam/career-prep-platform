import { useMemo, useRef, useState } from 'react'
import clsx from 'clsx'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Clock,
  Info,
  Loader2,
  RotateCcw,
  SlidersHorizontal,
  Sparkles,
  X,
} from 'lucide-react'
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

interface Settings {
  topic: string
  difficulty: 'easy' | 'medium' | 'hard'
  count: number
  type: string
}

// Keep in sync with QUESTION_TYPES in backend/app/agents/quiz_agent.py
const QUESTION_TYPES = [
  { id: 'mixed', label: 'Mix-up', desc: 'Concepts, real-world scenarios, code reading and tricky questions blended together.' },
  { id: 'interview', label: 'Interview style', desc: 'What interviewers actually ask: why, when and trade-offs.' },
  { id: 'assessment', label: 'Assessment style', desc: 'Online-test / screening round: crisp, timed, one clear answer.' },
  { id: 'most_asked', label: 'Most asked', desc: 'Classic, high-frequency questions on the topic. Based on commonly asked patterns the AI knows, not live interview data.' },
  { id: 'conceptual', label: 'Conceptual', desc: 'Fundamentals and how things work under the hood.' },
  { id: 'practical', label: 'Practical / scenario', desc: 'Real-world situations, debugging and design choices.' },
  { id: 'coding', label: 'Code & output', desc: 'Read code, predict the output, spot the bug.' },
]
const COUNTS = [5, 10, 15, 20]
const DIFFICULTIES = [
  { value: 'easy', label: 'Easy', dot: 'bg-emerald-400' },
  { value: 'medium', label: 'Medium', dot: 'bg-amber-400' },
  { value: 'hard', label: 'Hard', dot: 'bg-rose-400' },
] as const
const TOPIC_SUGGESTIONS = ['Data Structures', 'Algorithms', 'SQL', 'System Design', 'Python', 'JavaScript', 'Operating Systems', 'React']

const DEFAULTS: Settings = { topic: 'Data Structures', difficulty: 'medium', count: 5, type: 'mixed' }
const STORAGE_KEY = 'quiz_settings_v1'

function loadSettings(): Settings {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (!raw || typeof raw !== 'object') return DEFAULTS
    return {
      topic: typeof raw.topic === 'string' && raw.topic.trim() ? raw.topic.slice(0, 200) : DEFAULTS.topic,
      difficulty: ['easy', 'medium', 'hard'].includes(raw.difficulty) ? raw.difficulty : DEFAULTS.difficulty,
      count: COUNTS.includes(raw.count) ? raw.count : DEFAULTS.count,
      type: QUESTION_TYPES.some((t) => t.id === raw.type) ? raw.type : DEFAULTS.type,
    }
  } catch {
    return DEFAULTS
  }
}

const typeLabel = (id?: string) => QUESTION_TYPES.find((t) => t.id === id)?.label || 'Mix-up'

/* ------------------------------------------------------------------ small pieces */

function Segmented<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: { value: T; label: string; dot?: string }[]
  onChange: (v: T) => void
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="grid gap-1 rounded-lg bg-black/40 p-1 border border-zinc-800"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {options.map((o) => {
        const active = value === o.value
        return (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={clsx(
              'flex items-center justify-center gap-1.5 rounded-md py-1.5 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70',
              active ? 'bg-white text-black font-medium shadow' : 'text-zinc-400 hover:text-white hover:bg-white/5',
            )}
          >
            {o.dot && <span className={clsx('h-1.5 w-1.5 rounded-full', o.dot)} />}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

function Chip({ children, tone = 'zinc' }: { children: React.ReactNode; tone?: 'zinc' | 'blue' | 'amber' }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs border',
        tone === 'zinc' && 'bg-zinc-800/60 border-zinc-700/60 text-zinc-300',
        tone === 'blue' && 'bg-blue-500/10 border-blue-500/30 text-blue-300',
        tone === 'amber' && 'bg-amber-500/10 border-amber-500/30 text-amber-300',
      )}
    >
      {children}
    </span>
  )
}

function QuestionText({ text }: { text: string }) {
  return (
    <div className="space-y-2">
      {splitCodeFences(text).map((part, i) =>
        part.code ? (
          <pre
            key={i}
            className="text-xs bg-black/50 border border-zinc-800 rounded-lg p-3 overflow-x-auto font-mono text-zinc-200 whitespace-pre"
          >
            {part.text}
          </pre>
        ) : (
          <p key={i} className="whitespace-pre-wrap leading-relaxed">
            {part.text}
          </p>
        ),
      )}
    </div>
  )
}

function ScoreRing({ percent }: { percent: number }) {
  const r = 40
  const c = 2 * Math.PI * r
  const color = percent >= 80 ? '#34d399' : percent >= 50 ? '#fbbf24' : '#fb7185'
  return (
    <svg width="104" height="104" viewBox="0 0 104 104" role="img" aria-label={`Score ${percent} percent`}>
      <circle cx="52" cy="52" r={r} fill="none" stroke="#27272a" strokeWidth="9" />
      <circle
        cx="52"
        cy="52"
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="9"
        strokeLinecap="round"
        strokeDasharray={`${(percent / 100) * c} ${c}`}
        transform="rotate(-90 52 52)"
        style={{ transition: 'stroke-dasharray 600ms ease' }}
      />
      <text x="52" y="58" textAnchor="middle" fontSize="22" fontWeight="600" fill="#fafafa">
        {percent}%
      </text>
    </svg>
  )
}

function SkeletonCards({ n }: { n: number }) {
  return (
    <div className="space-y-4" aria-hidden="true">
      {Array.from({ length: Math.min(3, n) }).map((_, i) => (
        <div key={i} className="rounded-2xl border border-zinc-800 bg-[#111113] p-5 animate-pulse">
          <div className="h-3 w-20 rounded bg-zinc-800 mb-4" />
          <div className="h-4 w-3/4 rounded bg-zinc-800 mb-5" />
          <div className="space-y-2">
            {[0, 1, 2, 3].map((j) => (
              <div key={j} className="h-10 rounded-lg bg-zinc-800/60" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ page */

export default function Quizzes() {
  const [settings, setSettings] = useState<Settings>(loadSettings)
  const [settingsOpen, setSettingsOpen] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [questions, setQuestions] = useState<Q[]>([])
  const [meta, setMeta] = useState<{ type: string; difficulty: string; requested: number; topic: string } | null>(null)
  const [outdatedBackend, setOutdatedBackend] = useState(false)
  const [answers, setAnswers] = useState<Record<number, number>>({})
  const [submitted, setSubmitted] = useState(false)
  const [onlyWrong, setOnlyWrong] = useState(false)
  const quizTop = useRef<HTMLDivElement>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings((s) => {
      const next = { ...s, [key]: value }
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch {
        /* storage unavailable: settings just won't persist */
      }
      return next
    })
  }
  const resetSettings = () => {
    setSettings(DEFAULTS)
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
  }

  const typeInfo = QUESTION_TYPES.find((t) => t.id === settings.type) || QUESTION_TYPES[0]
  const diffInfo = DIFFICULTIES.find((d) => d.value === settings.difficulty) || DIFFICULTIES[1]

  const generate = async () => {
    if (loading) return // ignore double clicks: every request is an LLM call
    const topic = settings.topic.trim()
    if (topic.length < 2) {
      setError('Please enter a topic (at least 2 characters).')
      return
    }
    setLoading(true)
    setError(null)
    setSubmitted(false)
    setOnlyWrong(false)
    setAnswers({})
    try {
      const data = await api<QuizResponse>('/api/v1/quizzes/generate', {
        method: 'POST',
        body: JSON.stringify({
          topic,
          difficulty: settings.difficulty,
          num_questions: settings.count,
          question_type: settings.type,
        }),
      })
      setQuestions(data.questions || [])
      // A backend that predates quiz options doesn't echo these fields back.
      setOutdatedBackend(data.question_type === undefined)
      setMeta({
        type: data.question_type || settings.type,
        difficulty: data.difficulty || settings.difficulty,
        requested: data.num_requested || settings.count,
        topic: data.topic || topic,
      })
      if (!window.matchMedia('(min-width: 1024px)').matches) setSettingsOpen(false)
      setTimeout(() => quizTop.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    } catch (e: any) {
      setError(e.message || 'Failed to generate quiz')
    } finally {
      setLoading(false)
    }
  }

  const retake = () => {
    setAnswers({})
    setSubmitted(false)
    setOnlyWrong(false)
    quizTop.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const submit = () => {
    setSubmitted(true)
    setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }

  const answered = Object.keys(answers).length
  const score = questions.reduce((acc, q, i) => acc + (answers[i] === q.correct_index ? 1 : 0), 0)
  const percent = questions.length ? Math.round((score / questions.length) * 100) : 0
  const verdict =
    percent >= 80 ? 'Excellent work' : percent >= 60 ? 'Good job' : percent >= 40 ? 'Keep practicing' : 'Needs more review'

  const breakdown = useMemo(() => {
    const map = new Map<string, { right: number; total: number }>()
    questions.forEach((q, i) => {
      const key = q.category || 'General'
      const row = map.get(key) || { right: 0, total: 0 }
      row.total += 1
      if (answers[i] === q.correct_index) row.right += 1
      map.set(key, row)
    })
    return Array.from(map.entries())
  }, [questions, answers])

  const visible = questions.map((q, i) => ({ q, i })).filter(({ q, i }) => !(submitted && onlyWrong) || answers[i] !== q.correct_index)

  return (
    <div className="p-5 sm:p-8 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Practice Quizzes</h1>
        <p className="text-zinc-400 mt-1">Sharpen your skills with AI-generated multiple-choice quizzes.</p>
      </div>

      <div className="grid gap-6 grid-cols-[minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_340px] items-start">
        {/* ------------------------------------------------ right: settings (first on mobile) */}
        <aside className="min-w-0 order-first lg:order-last lg:sticky lg:top-6">
          <div className="rounded-2xl border border-zinc-800 bg-[#111113] overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <button
                type="button"
                onClick={() => setSettingsOpen((o) => !o)}
                aria-expanded={settingsOpen}
                aria-controls="quiz-settings"
                className="flex items-center gap-2 text-sm font-medium lg:cursor-default"
              >
                <SlidersHorizontal className="h-4 w-4 text-zinc-400" />
                Quiz settings
                <ChevronDown className={clsx('h-4 w-4 text-zinc-500 transition lg:hidden', settingsOpen && 'rotate-180')} />
              </button>
              <button
                type="button"
                onClick={resetSettings}
                className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-200 transition"
              >
                <RotateCcw className="h-3 w-3" /> Reset
              </button>
            </div>

            <div id="quiz-settings" className={clsx('p-5 space-y-5', !settingsOpen && 'hidden lg:block')}>
              <div>
                <label htmlFor="quiz-topic" className="block text-xs font-medium text-zinc-400 mb-2">
                  Topic
                </label>
                <input
                  id="quiz-topic"
                  value={settings.topic}
                  onChange={(e) => update('topic', e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && generate()}
                  maxLength={200}
                  placeholder="e.g. System Design, Python, SQL"
                  className="w-full bg-black/40 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-blue-500/60 focus:ring-2 focus:ring-blue-500/20"
                />
                <div className="flex flex-wrap gap-1.5 mt-2.5">
                  {TOPIC_SUGGESTIONS.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => update('topic', t)}
                      className={clsx(
                        'text-xs rounded-full px-2.5 py-1 border transition',
                        settings.topic === t
                          ? 'border-blue-500/50 bg-blue-500/10 text-blue-300'
                          : 'border-zinc-800 text-zinc-400 hover:text-white hover:border-zinc-600',
                      )}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className="text-xs font-medium text-zinc-400 mb-2">Difficulty</div>
                <Segmented
                  label="Difficulty"
                  value={settings.difficulty}
                  options={DIFFICULTIES.map((d) => ({ value: d.value, label: d.label, dot: d.dot }))}
                  onChange={(v) => update('difficulty', v)}
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-medium text-zinc-400">Number of questions</div>
                  <div className="flex items-center gap-1 text-xs text-zinc-500">
                    <Clock className="h-3 w-3" /> about {settings.count} min
                  </div>
                </div>
                <Segmented
                  label="Number of questions"
                  value={settings.count}
                  options={COUNTS.map((n) => ({ value: n, label: String(n) }))}
                  onChange={(v) => update('count', v)}
                />
              </div>

              <div>
                <label htmlFor="quiz-type" className="block text-xs font-medium text-zinc-400 mb-2">
                  Type of questions
                </label>
                <div className="relative">
                  <select
                    id="quiz-type"
                    value={settings.type}
                    onChange={(e) => update('type', e.target.value)}
                    className="w-full appearance-none bg-black/40 border border-zinc-800 rounded-lg pl-3 pr-9 py-2 text-sm text-white focus:outline-none focus:border-blue-500/60 focus:ring-2 focus:ring-blue-500/20"
                  >
                    {QUESTION_TYPES.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                </div>
                <p className="mt-2 flex gap-1.5 text-xs text-zinc-500 leading-relaxed">
                  <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                  {typeInfo.desc}
                </p>
              </div>

              <button
                type="button"
                onClick={generate}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 bg-white text-black font-medium rounded-lg py-2.5 text-sm hover:bg-zinc-200 disabled:opacity-60 disabled:cursor-not-allowed transition focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Generating…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" /> Generate {settings.count} questions
                  </>
                )}
              </button>
              <p className="text-center text-xs text-zinc-500 -mt-2">
                {typeInfo.label} · {diffInfo.label} · {settings.count} questions
              </p>
            </div>
          </div>
        </aside>

        {/* ------------------------------------------------ left: quiz */}
        <div className="min-w-0 scroll-mt-4" ref={quizTop}>
          {error && (
            <div role="alert" className="mb-4 flex gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>{error}</div>
            </div>
          )}

          {loading && (
            <div>
              <div className="mb-4 flex items-center gap-2 text-sm text-zinc-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                Writing {settings.count} {typeInfo.label.toLowerCase()} questions on {settings.topic.trim() || 'your topic'}…
                {settings.count > 10 && <span className="text-zinc-500">bigger quizzes can take 20–30 seconds</span>}
              </div>
              <SkeletonCards n={settings.count} />
            </div>
          )}

          {!loading && questions.length === 0 && (
            <div className="rounded-2xl border border-dashed border-zinc-800 bg-[#0e0e10] p-10 text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-blue-500/10 text-blue-400">
                <Sparkles className="h-6 w-6" />
              </div>
              <h2 className="text-lg font-medium">Ready when you are</h2>
              <p className="mt-1 text-sm text-zinc-400">Choose your settings on the right, then generate a quiz.</p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                <Chip tone="blue">{settings.topic.trim() || 'Topic'}</Chip>
                <Chip>{typeInfo.label}</Chip>
                <Chip>{diffInfo.label}</Chip>
                <Chip>{settings.count} questions</Chip>
              </div>
            </div>
          )}

          {!loading && questions.length > 0 && meta && (
            <div className="space-y-5">
              {outdatedBackend && (
                <div className="flex gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-sm">
                  <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                  <div>
                    Your server is running an older quiz version, so the question type and count options may be ignored.
                    Update <code>backend/app/agents/quiz_agent.py</code> and <code>backend/app/api/quizzes.py</code>, then
                    restart the backend.
                  </div>
                </div>
              )}

              <div className="rounded-2xl border border-zinc-800 bg-[#111113] p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-medium mr-1">{meta.topic}</h2>
                  <Chip tone="blue">{typeLabel(meta.type)}</Chip>
                  <Chip><span className="capitalize">{meta.difficulty}</span></Chip>
                  <Chip>{questions.length} questions</Chip>
                  {questions.length < meta.requested && (
                    <Chip tone="amber">
                      <AlertTriangle className="h-3 w-3" /> {questions.length} of {meta.requested} requested
                    </Chip>
                  )}
                </div>
                {questions.length < meta.requested && (
                  <p className="mt-2 text-xs text-amber-300/80">
                    The AI couldn't produce all {meta.requested} questions this time. Generate again for a full set.
                  </p>
                )}
                <div className="mt-4">
                  <div className="flex justify-between text-xs text-zinc-500 mb-1.5">
                    <span>
                      {answered} of {questions.length} answered
                    </span>
                    <span>{Math.round((answered / questions.length) * 100)}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-blue-500 transition-all duration-300"
                      style={{ width: `${(answered / questions.length) * 100}%` }}
                    />
                  </div>
                </div>
              </div>

              {submitted && (
                <div ref={resultRef} className="rounded-2xl border border-zinc-800 bg-[#111113] p-5 scroll-mt-4">
                  <div className="flex flex-wrap items-center gap-6">
                    <ScoreRing percent={percent} />
                    <div className="flex-1 min-w-[200px]">
                      <div className="text-xl font-semibold">{verdict}</div>
                      <div className="text-sm text-zinc-400 mt-0.5">
                        You got <span className="text-white font-medium">{score}</span> of {questions.length} right.
                      </div>
                      {breakdown.length > 1 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {breakdown.map(([cat, v]) => (
                            <Chip key={cat} tone={v.right === v.total ? 'blue' : 'zinc'}>
                              {cat} {v.right}/{v.total}
                            </Chip>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="mt-5 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={generate}
                      disabled={loading}
                      className="flex items-center gap-1.5 bg-white text-black text-sm font-medium rounded-lg px-4 py-2 hover:bg-zinc-200 disabled:opacity-60"
                    >
                      <Sparkles className="h-4 w-4" /> New quiz
                    </button>
                    <button
                      type="button"
                      onClick={retake}
                      className="flex items-center gap-1.5 text-sm rounded-lg px-4 py-2 border border-zinc-700 text-zinc-200 hover:bg-white/5"
                    >
                      <RotateCcw className="h-4 w-4" /> Retake these
                    </button>
                    {score < questions.length && (
                      <label className="ml-auto flex items-center gap-2 text-sm text-zinc-400 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={onlyWrong}
                          onChange={(e) => setOnlyWrong(e.target.checked)}
                          className="accent-blue-500"
                        />
                        Show only incorrect
                      </label>
                    )}
                  </div>
                </div>
              )}

              {visible.map(({ q, i }) => {
                const picked = answers[i]
                const right = picked === q.correct_index
                return (
                  <section
                    key={q.id || i}
                    className={clsx(
                      'rounded-2xl border bg-[#111113] p-5 transition',
                      submitted ? (right ? 'border-emerald-500/30' : 'border-red-500/30') : 'border-zinc-800',
                    )}
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-800 text-xs font-medium text-zinc-300">
                        {i + 1}
                      </span>
                      {q.category && (
                        <span className="text-[11px] uppercase tracking-wide text-zinc-400 bg-zinc-800/70 rounded px-2 py-0.5">
                          {q.category}
                        </span>
                      )}
                      {submitted && (
                        <span
                          className={clsx(
                            'ml-auto flex items-center gap-1 text-xs font-medium',
                            right ? 'text-emerald-400' : 'text-red-400',
                          )}
                        >
                          {right ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
                          {right ? 'Correct' : picked === undefined ? 'Unanswered' : 'Incorrect'}
                        </span>
                      )}
                    </div>

                    <div className="text-[15px] font-medium text-zinc-100 mb-4">
                      <QuestionText text={q.question} />
                    </div>

                    <div className="space-y-2" role="radiogroup" aria-label={`Question ${i + 1} options`}>
                      {(q.options || []).map((opt, oi) => {
                        const selected = picked === oi
                        const isCorrect = oi === q.correct_index
                        let cls = 'border-zinc-800 hover:border-zinc-600 hover:bg-white/[0.02]'
                        if (submitted) {
                          if (isCorrect) cls = 'border-emerald-500/50 bg-emerald-500/10'
                          else if (selected) cls = 'border-red-500/50 bg-red-500/10'
                          else cls = 'border-zinc-800 opacity-70'
                        } else if (selected) {
                          cls = 'border-blue-500/60 bg-blue-500/10'
                        }
                        return (
                          <button
                            key={oi}
                            type="button"
                            role="radio"
                            aria-checked={selected}
                            disabled={submitted}
                            onClick={() => setAnswers((a) => ({ ...a, [i]: oi }))}
                            className={clsx(
                              'w-full flex items-start gap-3 text-left text-sm px-3 py-2.5 rounded-lg border transition focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70',
                              cls,
                            )}
                          >
                            <span
                              className={clsx(
                                'mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-medium',
                                submitted && isCorrect
                                  ? 'border-emerald-400 bg-emerald-400 text-black'
                                  : submitted && selected
                                    ? 'border-red-400 bg-red-400 text-black'
                                    : selected
                                      ? 'border-blue-400 bg-blue-400 text-black'
                                      : 'border-zinc-600 text-zinc-400',
                              )}
                            >
                              {submitted && isCorrect ? (
                                <Check className="h-3 w-3" />
                              ) : submitted && selected ? (
                                <X className="h-3 w-3" />
                              ) : (
                                'ABCD'[oi]
                              )}
                            </span>
                            <span className="min-w-0 flex-1 whitespace-pre-wrap text-zinc-200">{opt}</span>
                          </button>
                        )
                      })}
                    </div>

                    {submitted && q.explanation && (
                      <div className="mt-4 rounded-lg bg-black/30 border border-zinc-800 px-3.5 py-3 text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">
                        <span className="block text-[11px] uppercase tracking-wide text-zinc-500 mb-1">Explanation</span>
                        {q.explanation}
                      </div>
                    )}
                  </section>
                )
              })}

              {submitted && visible.length === 0 && (
                <div className="text-center text-sm text-zinc-500 py-6">Nothing to show: every answer was correct.</div>
              )}

              {!submitted && (
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <button
                    type="button"
                    onClick={submit}
                    disabled={answered === 0}
                    className="bg-white text-black font-medium px-6 py-2.5 rounded-lg text-sm hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Submit answers
                  </button>
                  <span className="text-xs text-zinc-500">
                    {answered === questions.length
                      ? 'All answered. Ready to submit.'
                      : answered === 0
                        ? 'Answer at least one question to submit.'
                        : `${questions.length - answered} unanswered will be marked wrong.`}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
