import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export default function AuthCallback() {
  const { setTokens } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const hash = window.location.hash.slice(1)
    const params = new URLSearchParams(hash)
    const access = params.get('access_token')
    const refresh = params.get('refresh_token')

    if (!access || !refresh) {
      setError('Missing tokens from OAuth provider')
      return
    }

    setTokens(access, refresh)
      .then(() => navigate('/home', { replace: true }))
      .catch((e) => setError(e.message || 'Failed to complete login'))
  }, [setTokens, navigate])

  if (error) {
    return (
      <div className="min-h-screen bg-[#0a0a0b] flex items-center justify-center text-white">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error}</p>
          <a href="/signin" className="text-sm text-zinc-400 hover:text-white underline">
            Back to sign in
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0a0a0b] flex items-center justify-center text-zinc-400">
      Completing sign in…
    </div>
  )
}
