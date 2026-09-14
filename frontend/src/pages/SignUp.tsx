import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { authApi } from '../lib/api'

export default function SignUp() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await register(email, password, name || undefined)
      navigate('/home')
    } catch (err: any) {
      setError(err.message || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0b] flex flex-col">
      <header className="px-8 py-5">
        <Link to="/" className="text-lg font-semibold text-white">
          careerprep
        </Link>
      </header>
      <div className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-[#111113] border border-zinc-800 rounded-xl p-8">
          <h1 className="text-2xl font-semibold text-white mb-1">Create your account</h1>
          <p className="text-sm text-zinc-400 mb-6">Start preparing for better opportunities.</p>

          {error && (
            <div className="mb-4 p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
              {error}
            </div>
          )}

          <form className="space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="block text-sm text-zinc-400 mb-1.5">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="John Doe"
                className="w-full bg-[#0a0a0b] border border-zinc-700 rounded-md px-3 py-2.5 text-white placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-zinc-400 mb-1.5">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-[#0a0a0b] border border-zinc-700 rounded-md px-3 py-2.5 text-white placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-zinc-400 mb-1.5">Password</label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-[#0a0a0b] border border-zinc-700 rounded-md px-3 py-2.5 text-white placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-white text-black font-medium py-2.5 rounded-md hover:bg-zinc-200 transition mt-2 disabled:opacity-60"
            >
              {loading ? 'Creating…' : 'Create account'}
            </button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-zinc-800" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-[#111113] px-2 text-zinc-500">or</span>
            </div>
          </div>

          <div className="space-y-3">
            <a
              href={authApi.googleLoginUrl()}
              className="w-full flex items-center justify-center gap-2 border border-zinc-700 rounded-md py-2.5 text-sm text-zinc-200 hover:border-zinc-500 transition"
            >
              Continue with Google
            </a>
            <a
              href={authApi.githubLoginUrl()}
              className="w-full flex items-center justify-center gap-2 border border-zinc-700 rounded-md py-2.5 text-sm text-zinc-200 hover:border-zinc-500 transition"
            >
              Continue with GitHub
            </a>
          </div>

          <p className="mt-6 text-center text-sm text-zinc-500">
            Already have an account?{' '}
            <Link to="/signin" className="text-white hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
