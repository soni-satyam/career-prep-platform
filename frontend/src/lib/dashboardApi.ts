// Dashboard + tracker API client. Self-contained: only depends on the generic `api` helper.
import { api } from './api'

export type ApplicationStatus = 'applied' | 'interviewing' | 'offer' | 'rejected' | 'withdrawn'
export const STATUSES: Array<{ key: ApplicationStatus; label: string }> = [
  { key: 'applied', label: 'Applied' },
  { key: 'interviewing', label: 'Interviewing' },
  { key: 'offer', label: 'Offer' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'withdrawn', label: 'Withdrawn' },
]

export interface ResumeStatus {
  uploaded: boolean
  filename: string | null
  title: string
  skills_count: number
  experience_years: number | null
  updated_at: string | null
  age_days: number | null
  stale: boolean
  completeness: number
  next_steps: string[]
}

export interface Application {
  id: number
  job_uid: string | null
  title: string
  company: string
  location: string
  url: string
  source_label: string
  status: ApplicationStatus
  applied_on: string | null
  next_step: string
  next_step_date: string | null
  notes: string
  created_at: string
  updated_at: string
}

export interface SavedJob {
  id: number
  job_uid: string
  title: string
  company: string
  location: string
  url: string
  source: string
  source_label: string
  posted_at: string | null
  salary_text: string
  match_score: number | null
  created_at: string
}

export interface ActivityItem {
  id: string
  type: string
  title: string
  subtitle: string
  link: string
  at: string
}

export interface DashboardData {
  resume: ResumeStatus
  stats: {
    saved_jobs: number
    applications: number
    active: number
    interviewing: number
    offers: number
    rejected: number
    prep_sessions: number
    by_status: Record<string, number>
  }
  activity: ActivityItem[]
  saved_jobs: SavedJob[]
  applications: Application[]
  upcoming: Application[]
  follow_up: Application[]
}

/** The few job fields the dashboard needs (a subset of the job-search result). */
export interface TrackableJob {
  id: string
  title: string
  company: string
  location: string
  url: string
  source: string
  source_label: string
  posted_at: string | null
  salary_min?: number | null
  salary_max?: number | null
  salary_currency?: string
  salary_text?: string
  work_mode?: string
  remote?: boolean
  match: { score: number; matched_skills: string[]; missing_skills: string[] } | null
}

export interface RecommendedData {
  jobs: TrackableJob[]
  reason: 'ok' | 'no_resume' | 'no_results'
  based_on: string
  saved_ids: string[]
  applied_ids: string[]
}

export interface NewApplication {
  title: string
  company?: string
  location?: string
  url?: string
  source_label?: string
  job_uid?: string
  status?: ApplicationStatus
  applied_on?: string
}

export interface ApplicationPatch {
  title?: string
  company?: string
  status?: ApplicationStatus
  applied_on?: string
  next_step?: string
  next_step_date?: string
  notes?: string
  clear_next_step_date?: boolean
}

export const dashboardApi = {
  get: () => api<DashboardData>('/api/v1/dashboard'),
  recommended: (limit = 6) => api<RecommendedData>(`/api/v1/dashboard/recommended?limit=${limit}`),
}

export const trackerApi = {
  savedIds: () => api<{ saved: string[]; applied: string[] }>('/api/v1/tracker/saved/ids'),
  save: (job: TrackableJob) =>
    api<SavedJob>('/api/v1/tracker/saved', {
      method: 'POST',
      body: JSON.stringify({
        job_uid: job.id,
        title: job.title,
        company: job.company || '',
        location: job.location || '',
        url: job.url || '',
        source: job.source || '',
        source_label: job.source_label || '',
        posted_at: job.posted_at,
        salary_text: job.salary_text || '',
        match_score: job.match?.score ?? null,
      }),
    }),
  unsave: (uid: string) => api<{ ok: boolean }>(`/api/v1/tracker/saved/${encodeURIComponent(uid)}`, { method: 'DELETE' }),
  listApplications: (status?: string) =>
    api<Application[]>(`/api/v1/tracker/applications${status ? `?status=${status}` : ''}`),
  addApplication: (body: NewApplication) =>
    api<Application>('/api/v1/tracker/applications', { method: 'POST', body: JSON.stringify(body) }),
  updateApplication: (id: number, body: ApplicationPatch) =>
    api<Application>(`/api/v1/tracker/applications/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteApplication: (id: number) => api<{ ok: boolean }>(`/api/v1/tracker/applications/${id}`, { method: 'DELETE' }),
}
