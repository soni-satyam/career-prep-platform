import { Routes, Route, Navigate } from 'react-router-dom'
import Landing from './pages/Landing'
import SignUp from './pages/SignUp'
import SignIn from './pages/SignIn'
import AuthCallback from './pages/AuthCallback'
import Dashboard from './pages/Dashboard'
import Admin from './pages/Admin'
import ResumeTailor from './pages/ResumeTailor'
import InterviewPrep from './pages/InterviewPrep'
import SessionDetail from './pages/SessionDetail'
import Settings from './pages/Settings'
import Jobs from './pages/Jobs'
import Companies from './pages/Companies'
import ProgressPage from './pages/Progress'
import Quizzes from './pages/Quizzes'
import LiveInterview from './pages/LiveInterview'
import AppLayout from './components/AppLayout'
import { useAuth } from './lib/auth'

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0b] flex items-center justify-center text-zinc-400">
        Loading…
      </div>
    )
  }
  if (!user) return <Navigate to="/signin" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/signup" element={<SignUp />} />
      <Route path="/signin" element={<SignIn />} />
      <Route path="/auth/callback" element={<AuthCallback />} />

      <Route
        element={
          <Protected>
            <AppLayout />
          </Protected>
        }
      >
        <Route path="/home" element={<Dashboard />} />
        <Route path="/resume" element={<ResumeTailor />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/jobs/:id" element={<Jobs />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/interview" element={<InterviewPrep />} />
        <Route path="/live-interview" element={<LiveInterview />} />
        <Route path="/quizzes" element={<Quizzes />} />
        <Route path="/progress" element={<ProgressPage />} />
        <Route path="/sessions/:id" element={<SessionDetail />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/admin" element={<Admin />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function Placeholder({ title }: { title: string }) {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-white mb-2">{title}</h1>
      <p className="text-zinc-400">Coming soon.</p>
    </div>
  )
}
