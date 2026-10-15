export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return d === 1 ? 'yesterday' : `${d}d ago`
  const mo = Math.floor(d / 30)
  return mo < 12 ? `${mo}mo ago` : `${Math.floor(mo / 12)}y ago`
}

/** 'YYYY-MM-DD' -> 'in 3 days' / 'today' / '2 days ago' (date-only, no timezone drift). */
export function dayDelta(date: string | null | undefined): string {
  if (!date) return ''
  const [y, m, d] = date.split('-').map(Number)
  const target = new Date(y, m - 1, d).getTime()
  const t = new Date()
  const today = new Date(t.getFullYear(), t.getMonth(), t.getDate()).getTime()
  const days = Math.round((target - today) / 86_400_000)
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days === -1) return 'yesterday'
  return days > 0 ? `in ${days} days` : `${-days} days ago`
}

export function shortDate(date: string | null | undefined): string {
  if (!date) return ''
  const [y, m, d] = date.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

export const STATUS_STYLE: Record<string, string> = {
  applied: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  interviewing: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  offer: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  rejected: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  withdrawn: 'bg-zinc-800 text-zinc-500 border-zinc-700',
}

export const card = 'bg-[#111113] border border-zinc-800 rounded-xl p-5'
export const inputCls =
  'w-full bg-[#0c0c0e] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600'
