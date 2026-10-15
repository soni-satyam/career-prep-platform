// Tiny shared store: which jobs are saved / applied. Lets a Save button on the Jobs page and
// on the dashboard stay in sync without prop drilling. Mutations broadcast TRACKER_EVENT so
// the dashboard can reload its numbers.
import { useSyncExternalStore } from 'react'
import { trackerApi, type TrackableJob } from './dashboardApi'

export const TRACKER_EVENT = 'careerprep:tracker-changed'

interface State {
  saved: ReadonlySet<string>
  applied: ReadonlySet<string>
  loaded: boolean
}

let state: State = { saved: new Set(), applied: new Set(), loaded: false }
let loading: Promise<void> | null = null
const listeners = new Set<() => void>()

function set(next: Partial<State>) {
  state = { ...state, ...next }
  listeners.forEach((l) => l())
}

function announce() {
  window.dispatchEvent(new Event(TRACKER_EVENT))
}

export function loadJobState(force = false): Promise<void> {
  if (state.loaded && !force) return Promise.resolve()
  if (!loading) {
    loading = trackerApi
      .savedIds()
      .then((r) => set({ saved: new Set(r.saved), applied: new Set(r.applied), loaded: true }))
      .catch(() => set({ loaded: true }))
      .finally(() => {
        loading = null
      })
  }
  return loading
}

export function useJobState(): State {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => state
  )
}

export async function toggleSaved(job: TrackableJob): Promise<void> {
  const was = state.saved.has(job.id)
  const next = new Set(state.saved)
  if (was) next.delete(job.id)
  else next.add(job.id)
  set({ saved: next })                       // optimistic
  try {
    if (was) await trackerApi.unsave(job.id)
    else await trackerApi.save(job)
    announce()
  } catch (e) {
    const undo = new Set(state.saved)
    if (was) undo.add(job.id)
    else undo.delete(job.id)
    set({ saved: undo })
    throw e
  }
}

export async function markApplied(job: TrackableJob): Promise<void> {
  if (state.applied.has(job.id)) return
  set({ applied: new Set(state.applied).add(job.id) })
  try {
    await trackerApi.addApplication({
      title: job.title,
      company: job.company,
      location: job.location,
      url: job.url,
      source_label: job.source_label,
      job_uid: job.id,
      status: 'applied',
    })
    announce()
  } catch (e) {
    const undo = new Set(state.applied)
    undo.delete(job.id)
    set({ applied: undo })
    throw e
  }
}

export function seedJobState(saved: string[], applied: string[]) {
  set({ saved: new Set(saved), applied: new Set(applied), loaded: true })
}
