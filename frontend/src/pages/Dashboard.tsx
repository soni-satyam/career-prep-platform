import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { dashboardApi, type DashboardData } from '../lib/dashboardApi'
import { TRACKER_EVENT } from '../lib/jobState'
import ActivityFeed from '../components/dashboard/ActivityFeed'
import ApplicationTracker, { type TrackerHandle } from '../components/dashboard/ApplicationTracker'
import NudgesCard from '../components/dashboard/NudgesCard'
import QuickActions from '../components/dashboard/QuickActions'
import RecommendedJobs from '../components/dashboard/RecommendedJobs'
import ResumeStatusCard from '../components/dashboard/ResumeStatusCard'
import SavedJobs from '../components/dashboard/SavedJobs'
import StatTiles from '../components/dashboard/StatTiles'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

export default function Dashboard() {
  const { user } = useAuth()
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')
  const trackerRef = useRef<TrackerHandle>(null)
  const name = user?.full_name?.split(' ')[0] || 'there'

  const load = useCallback(async () => {
    try {
      setData(await dashboardApi.get())
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load your dashboard')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Save / "I applied" pressed anywhere (e.g. recommended jobs) -> refresh numbers and the tracker list.
  useEffect(() => {
    const onChange = () => {
      load()
      trackerRef.current?.reload()
    }
    window.addEventListener(TRACKER_EVENT, onChange)
    return () => window.removeEventListener(TRACKER_EVENT, onChange)
  }, [load])

  const refreshAll = () => {
    load()
    trackerRef.current?.reload()
  }

  return (
    <div className="p-4 sm:p-8 max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold mb-1">
          {greeting()}, {name}
        </h1>
        <p className="text-zinc-400">Here’s where your job search stands.</p>
      </div>

      {error && (
        <div className="p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm flex items-center justify-between gap-3">
          <span>{error}</span>
          <button onClick={load} className="underline shrink-0">
            Retry
          </button>
        </div>
      )}

      <QuickActions
        hasResume={!!data?.resume.uploaded}
        onResumeUploaded={refreshAll}
        onAddApplication={() => trackerRef.current?.openAdd()}
      />

      {!data && !error && <p className="text-sm text-zinc-500">Loading your dashboard…</p>}

      {data && (
        <>
          <StatTiles stats={data.stats} />

          <div className="grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <ApplicationTracker ref={trackerRef} counts={data.stats.by_status} onChanged={load} />
            </div>
            <div className="space-y-6">
              <ResumeStatusCard resume={data.resume} onChanged={refreshAll} />
              <NudgesCard upcoming={data.upcoming} followUp={data.follow_up} onChanged={refreshAll} />
            </div>
          </div>

          <RecommendedJobs hasResume={data.resume.uploaded} />

          <div className="grid lg:grid-cols-2 gap-6">
            <SavedJobs jobs={data.saved_jobs} total={data.stats.saved_jobs} onChanged={refreshAll} />
            <ActivityFeed items={data.activity} />
          </div>
        </>
      )}
    </div>
  )
}
