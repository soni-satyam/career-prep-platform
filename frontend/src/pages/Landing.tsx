import { Link } from 'react-router-dom'

const steps = [
  'Find Jobs',
  'Tailor Resume',
  'Practice Interviews',
  'Get Better',
  'Land Opportunities',
]

const trusted = ['Google', 'Microsoft', 'Amazon', 'Netflix', 'Adobe', 'Meta']

export default function Landing() {
  return (
    <div className="min-h-screen bg-[#0a0a0b] text-white">
      {/* Nav */}
      <header className="flex items-center justify-between px-8 py-5 border-b border-zinc-800/80">
        <div className="flex items-center gap-8">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            careerprep
          </Link>
          <nav className="hidden md:flex gap-6 text-sm text-zinc-400">
            <a href="#features" className="hover:text-white transition">Features</a>
            <a href="#pricing" className="hover:text-white transition">Pricing</a>
            <a href="#resources" className="hover:text-white transition">Resources</a>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/signin"
            className="text-sm text-zinc-300 hover:text-white px-3 py-1.5"
          >
            Sign in
          </Link>
          <Link
            to="/signup"
            className="text-sm bg-white text-black font-medium px-4 py-1.5 rounded-md hover:bg-zinc-200 transition"
          >
            Get started
          </Link>
        </div>
      </header>

      {/* Hero */}
      <main className="max-w-6xl mx-auto px-8 pt-20 pb-24">
        <div className="grid md:grid-cols-2 gap-16 items-start">
          <div>
            <h1 className="text-5xl md:text-6xl font-semibold tracking-tight leading-[1.1] mb-6">
              Prepare
              <br />
              for what&apos;s next.
            </h1>
            <p className="text-zinc-400 text-lg max-w-md mb-8 leading-relaxed">
              Tailor your resume, find real opportunities, practice interviews
              and quizzes — all in one place for your tech career.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/signup"
                className="inline-flex items-center gap-2 bg-white text-black font-medium px-5 py-2.5 rounded-md hover:bg-zinc-200 transition"
              >
                Get started →
              </Link>
              <button className="inline-flex items-center gap-2 border border-zinc-700 text-zinc-200 px-5 py-2.5 rounded-md hover:border-zinc-500 transition">
                ▶ Watch demo
              </button>
            </div>

            <div className="mt-16">
              <p className="text-xs text-zinc-500 uppercase tracking-wider mb-4">
                Trusted by learners from
              </p>
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-zinc-400">
                {trusted.map((c) => (
                  <span key={c}>{c}</span>
                ))}
              </div>
            </div>
          </div>

          {/* Steps card */}
          <div className="bg-[#111113] border border-zinc-800 rounded-xl p-6">
            <ol className="space-y-4">
              {steps.map((step, i) => (
                <li key={step} className="flex items-center gap-4">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-sm text-zinc-300">
                    {i + 1}
                  </span>
                  <span className="text-zinc-200">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </main>
    </div>
  )
}
