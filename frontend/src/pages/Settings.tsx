import { useEffect, useState } from 'react'
import { usersApi } from '../lib/api'
import { useAuth } from '../lib/auth'

export default function Settings() {
  const { user, setTokens } = useAuth()
  const [fullName, setFullName] = useState('')
  const [bio, setBio] = useState('')
  const [role, setRole] = useState('')
  const [location, setLocation] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (user) {
      setFullName(user.full_name || '')
      setBio(user.bio || '')
      setRole(user.current_role || '')
      setLocation(user.location || '')
    }
  }, [user])

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setMessage(null)
    setError(null)
    try {
      await usersApi.updateMe({
        full_name: fullName,
        bio,
        current_role: role,
        location,
      })
      // reload user via re-fetch me
      const access = localStorage.getItem('access_token')
      const refresh = localStorage.getItem('refresh_token')
      if (access && refresh) await setTokens(access, refresh)
      setMessage('Saved')
    } catch (err: any) {
      setError(err.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-8 max-w-lg">
      <h1 className="text-2xl font-semibold mb-1">Settings</h1>
      <p className="text-zinc-400 mb-8">Update your profile.</p>

      {message && <div className="mb-4 text-sm text-emerald-400">{message}</div>}
      {error && <div className="mb-4 text-sm text-red-400">{error}</div>}

      <form onSubmit={save} className="space-y-4">
        <div>
          <label className="block text-sm text-zinc-400 mb-1.5">Email</label>
          <input
            value={user?.email || ''}
            disabled
            className="w-full bg-zinc-900 border border-zinc-800 rounded-md px-3 py-2 text-sm text-zinc-500"
          />
        </div>
        <div>
          <label className="block text-sm text-zinc-400 mb-1.5">Name</label>
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-600"
          />
        </div>
        <div>
          <label className="block text-sm text-zinc-400 mb-1.5">Bio</label>
          <textarea
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            rows={3}
            className="w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-600"
          />
        </div>
        <div>
          <label className="block text-sm text-zinc-400 mb-1.5">Current role</label>
          <input
            value={role}
            onChange={(e) => setRole(e.target.value)}
            placeholder="e.g. Software Engineer"
            className="w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-600"
          />
        </div>
        <div>
          <label className="block text-sm text-zinc-400 mb-1.5">Location</label>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g. Bengaluru, India"
            className="w-full bg-[#111113] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-600"
          />
        </div>
        <button
          type="submit"
          disabled={saving}
          className="bg-white text-black font-medium px-5 py-2 rounded-md hover:bg-zinc-200 disabled:opacity-60"
        >
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </form>
    </div>
  )
}
