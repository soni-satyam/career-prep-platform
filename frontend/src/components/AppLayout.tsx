import { NavLink, Outlet, Link, useNavigate } from 'react-router-dom'
import {
  Home,
  FileText,
  Search,
  Building2,
  MessageSquare,
  Mic,
  HelpCircle,
  BarChart3,
  Settings,
  LogOut,
  Shield,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../lib/auth'
import { useFeatures } from '../lib/features'

const nav = [
  { to: '/home', label: 'Home', icon: Home, flag: null },
  { to: '/resume', label: 'Resume', icon: FileText, flag: 'resume_tailor' },
  { to: '/jobs', label: 'Job Search', icon: Search, flag: 'job_search' },
  { to: '/companies', label: 'Company Search', icon: Building2, flag: 'company_search' },
  { to: '/interview', label: 'Interview Prep', icon: MessageSquare, flag: 'interview_prep' },
  { to: '/live-interview', label: 'AI Interview', icon: Mic, flag: 'interview_prep' },
  { to: '/quizzes', label: 'Quizzes', icon: HelpCircle, flag: 'quizzes' },
  { to: '/progress', label: 'Progress', icon: BarChart3, flag: 'progress_tracking' },
]

export default function AppLayout() {
  const { user, logout, isAdmin } = useAuth()
  const { enabled } = useFeatures()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  const initial = (user?.full_name || user?.email || 'U')[0].toUpperCase()
  const visibleNav = nav.filter((n) => !n.flag || enabled(n.flag))

  return (
    <div className="flex h-screen bg-[#0a0a0b] text-white overflow-hidden">
      <aside className="w-56 shrink-0 border-r border-zinc-800 flex flex-col bg-[#0c0c0e]">
        <div className="px-5 py-5">
          <Link to="/home" className="text-lg font-semibold tracking-tight">
            careerprep
          </Link>
        </div>
        <nav className="flex-1 px-3 space-y-0.5">
          {visibleNav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition',
                  isActive
                    ? 'bg-zinc-800 text-white'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-900'
                )
              }
            >
              <Icon size={18} strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
          {isAdmin && (
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition',
                  isActive
                    ? 'bg-zinc-800 text-white'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-900'
                )
              }
            >
              <Shield size={18} strokeWidth={1.75} />
              Admin
            </NavLink>
          )}
        </nav>
        <div className="px-3 pb-5 space-y-0.5 border-t border-zinc-800 pt-3">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition',
                isActive
                  ? 'bg-zinc-800 text-white'
                  : 'text-zinc-400 hover:text-white hover:bg-zinc-900'
              )
            }
          >
            <Settings size={18} strokeWidth={1.75} />
            Settings
          </NavLink>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm text-zinc-400 hover:text-white hover:bg-zinc-900"
          >
            <LogOut size={18} strokeWidth={1.75} />
            Log out
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-zinc-800 flex items-center justify-between px-6 shrink-0">
          <div className="flex-1 max-w-md">
            <input
              type="search"
              placeholder="Search jobs, companies or skills..."
              className="w-full bg-zinc-900 border border-zinc-800 rounded-md px-3 py-1.5 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-zinc-600"
            />
          </div>
          <div className="flex items-center gap-3 ml-4">
            <span className="text-sm text-zinc-400 hidden sm:inline">
              {user?.full_name || user?.email}
            </span>
            <div className="h-8 w-8 rounded-full bg-blue-600 flex items-center justify-center text-sm font-medium">
              {initial}
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
