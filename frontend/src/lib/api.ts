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

export interface JobMatch {
  score: number
  matched_skills: string[]
  missing_skills: string[]
}

export interface JobResult {
  id: string
  title: string
  company: string
  location: string
  remote: boolean
  work_mode: string
  url: string
  source: string
  source_label: string
  source_tier: number
  posted_at: string | null
  snippet: string
  employment_type: string
  seniority: string
  salary_min: number | null
  salary_max: number | null
  salary_currency: string
  salary_text: string
  experience_min: number | null
  experience_max: number | null
  also_on: Array<{ source: string; label: string; url: string }>
  match: JobMatch | null
}

export interface JobSourceStatus {
  name: string
  status: 'ok' | 'skipped' | 'error'
  count: number
  message: string
}

export interface JobSearchResponse {
  results: JobResult[]
  total: number
  page: number
  page_size: number
  has_more: boolean
  sources: JobSourceStatus[]
  facets: Record<string, number>
  profile_used: boolean
}

export interface JobSearchParams {
  q?: string
  location?: string
  work_mode?: string
  salary_min?: number
  salary_currency?: string
  include_unspecified_salary?: boolean
  experience_min?: number
  experience_max?: number
  employment_type?: string
  posted_within_days?: number
  sources?: string[]
  sort?: string
  page?: number
  page_size?: number
}

export interface CandidateProfile {
  has_profile: boolean
  title: string
  skills: string[]
  experience_years: number | null
  source_filename: string | null
  updated_at: string | null
}

function toQuery(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)))
    else sp.append(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const jobsApi = {
  search: (params: JobSearchParams, signal?: AbortSignal) =>
    api<JobSearchResponse>(`/api/v1/jobs/search${toQuery({ ...params })}`, { signal }),
  meta: () =>
    api<{ sources: Array<{ key: string; label: string; tier: number }> }>('/api/v1/jobs/search/meta'),
  list: (q?: string) =>
    api<any[]>(`/api/v1/jobs${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  get: (id: number) => api<any>(`/api/v1/jobs/${id}`),
  companies: (q?: string) =>
    api<any[]>(`/api/v1/jobs/companies${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  company: (id: number) => api<any>(`/api/v1/jobs/companies/${id}`),
}

export const profileApi = {
  get: () => api<CandidateProfile>('/api/v1/profile'),
  uploadResume: (file?: File, text?: string) => {
    const fd = new FormData()
    if (file) fd.append('file', file)
    if (text) fd.append('text', text)
    return api<CandidateProfile>('/api/v1/profile/resume', { method: 'POST', body: fd })
  },
  update: (body: { title?: string; skills?: string[]; experience_years?: number }) =>
    api<CandidateProfile>('/api/v1/profile', { method: 'PATCH', body: JSON.stringify(body) }),
  remove: () => api<CandidateProfile>('/api/v1/profile', { method: 'DELETE' }),
}

export interface AtsScore {
  score: number
  matched: string[]
  missing: string[]
  total_terms: number
}

export interface AtsMatch {
  before: AtsScore | null
  after: AtsScore
  delta: number | null
  gained: string[]
  still_missing: string[]
  method: string
}

export interface ResumeTemplate {
  key: string
  label: string
  description: string
}

/** Authenticated file download (a plain <a href> cannot send the Bearer token). */
async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const token = localStorage.getItem('access_token')
  const res = await fetch(`${API_BASE}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `Download failed (${res.status})`)
  }
  const cd = res.headers.get('Content-Disposition') || ''
  const name = /filename="?([^";]+)"?/i.exec(cd)?.[1] || fallbackName
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export const prepApi = {
  resumeTemplates: () => api<{ default: string; templates: ResumeTemplate[] }>('/api/v1/prep/resume-templates'),
  downloadResumePdf: (sessionId: number, template: string, page: string) =>
    downloadFile(
      `/api/v1/prep/sessions/${sessionId}/export-pdf?template=${encodeURIComponent(template)}&page=${encodeURIComponent(page)}`,
      'Resume.pdf'
    ),
  downloadResumeHtml: (sessionId: number) =>
    downloadFile(`/api/v1/prep/sessions/${sessionId}/export-html`, `resume-${sessionId}.html`),
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
    // 'resume' / 'interview' skip agents the page never shows (fewer LLM calls)
    mode?: 'full' | 'resume' | 'interview'
  }) =>
    api<any>('/api/v1/prep/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  listSessions: () => api<any[]>('/api/v1/prep/sessions'),
  getSession: (id: number) => api<any>(`/api/v1/prep/sessions/${id}`),
}
