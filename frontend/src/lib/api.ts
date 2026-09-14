const API_BASE = import.meta.env.VITE_API_URL || ''

export async function api<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = localStorage.getItem('access_token')
  const headers: HeadersInit = {
    ...(options.headers || {}),
  }
  if (!(options.body instanceof FormData)) {
    ;(headers as Record<string, string>)['Content-Type'] = 'application/json'
  }
  if (token) {
    ;(headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = body.detail
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail) || res.statusText)
  }
  return res.json()
}

export interface User {
  id: number
  email: string
  full_name: string | null
  bio: string | null
  current_role: string | null
  location: string | null
  is_superuser: boolean
  oauth_provider: string | null
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export const authApi = {
  register: (email: string, password: string, full_name?: string) =>
    api<TokenPair>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name }),
    }),
  login: (email: string, password: string) =>
    api<TokenPair>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  refresh: (refresh_token: string) =>
    api<TokenPair>('/api/v1/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token }),
    }),
  me: () => api<User>('/api/v1/auth/me'),
  googleLoginUrl: () => `${API_BASE}/api/v1/auth/google/login`,
  githubLoginUrl: () => `${API_BASE}/api/v1/auth/github/login`,
}

export const usersApi = {
  updateMe: (data: { full_name?: string; bio?: string; current_role?: string; location?: string }) =>
    api<User>('/api/v1/users/me', { method: 'PATCH', body: JSON.stringify(data) }),
}

export const adminApi = {
  stats: () => api<{ total_users: number; total_sessions: number; active_features: number }>('/api/v1/admin/stats'),
  users: () => api<Array<{
    id: number
    email: string
    full_name: string | null
    is_active: boolean
    is_superuser: boolean
    oauth_provider: string | null
  }>>('/api/v1/admin/users'),
  toggleActive: (id: number) =>
    api<{ id: number; is_active: boolean }>(`/api/v1/admin/users/${id}/toggle-active`, { method: 'PATCH' }),
  toggleAdmin: (id: number) =>
    api<{ id: number; is_superuser: boolean }>(`/api/v1/admin/users/${id}/toggle-admin`, { method: 'PATCH' }),
  features: () =>
    api<Array<{ id: number; key: string; name: string; description: string | null; enabled: boolean }>>(
      '/api/v1/admin/features'
    ),
  updateFeature: (key: string, enabled: boolean) =>
    api(`/api/v1/admin/features/${key}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    }),
}

export const featuresApi = {
  list: () =>
    api<Array<{ key: string; name: string; description: string | null; enabled: boolean }>>(
      '/api/v1/features'
    ),
}

export const jobsApi = {
  list: (q?: string) =>
    api<any[]>(`/api/v1/jobs${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  get: (id: number) => api<any>(`/api/v1/jobs/${id}`),
  companies: (q?: string) =>
    api<any[]>(`/api/v1/jobs/companies${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  company: (id: number) => api<any>(`/api/v1/jobs/companies/${id}`),
}

export const prepApi = {
  analyzeJd: (jd_text: string) =>
    api('/api/v1/prep/analyze-jd', { method: 'POST', body: JSON.stringify({ jd_text }) }),
  extractProfile: (resume_text: string) =>
    api('/api/v1/prep/extract-profile', { method: 'POST', body: JSON.stringify({ resume_text }) }),
  analyzeGaps: (jd_analysis: object, profile: object) =>
    api('/api/v1/prep/analyze-gaps', {
      method: 'POST',
      body: JSON.stringify({ jd_analysis, profile }),
    }),
  tailorResume: (jd_analysis: object, profile: object, edit_instruction?: string) =>
    api('/api/v1/prep/tailor-resume', {
      method: 'POST',
      body: JSON.stringify({ jd_analysis, profile, edit_instruction }),
    }),
  interviewPack: (jd_analysis: object, profile: object, tailored_resume?: object) =>
    api('/api/v1/prep/interview-pack', {
      method: 'POST',
      body: JSON.stringify({ jd_analysis, profile, tailored_resume }),
    }),
  extractText: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api<{ filename: string; text: string; length: number }>('/api/v1/prep/extract-text', {
      method: 'POST',
      body: form,
    })
  },
  createSession: (data: {
    jd_text: string
    resume_text?: string
    target_role?: string
    company?: string
    title?: string
  }) =>
    api<any>('/api/v1/prep/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  listSessions: () => api<any[]>('/api/v1/prep/sessions'),
  getSession: (id: number) => api<any>(`/api/v1/prep/sessions/${id}`),
}
