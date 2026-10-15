import { useEffect, useRef } from 'react'
import { Check } from 'lucide-react'

export interface IndexChild {
  id: string
  label: string
  attention?: boolean // amber dot, e.g. "skills need checking"
}
export interface IndexItem {
  id: string
  label: string
  hint: string // one line of guidance, shown for the section you're on
  status?: 'done' | 'attention'
  badge?: { text: string; tone: 'good' | 'ok' | 'bad' | 'muted' }
  children?: IndexChild[]
}

const TONE: Record<string, string> = {
  good: 'text-emerald-300', ok: 'text-amber-300', bad: 'text-red-300', muted: 'text-zinc-500',
}

function Marker({ n, status, current }: { n: number; status?: IndexItem['status']; current: boolean }) {
  const base = 'w-6 h-6 shrink-0 rounded-full border flex items-center justify-center text-[11px] font-medium relative z-10 bg-[#0a0a0b]'
  if (status === 'done')
    return (
      <span className={`${base} border-emerald-500/60 text-emerald-300 bg-emerald-500/15`}>
        <Check size={13} />
      </span>
    )
  if (status === 'attention')
    return <span className={`${base} ${current ? 'border-amber-400 text-amber-300' : 'border-amber-500/60 text-amber-300'}`}>{n}</span>
  return <span className={`${base} ${current ? 'border-white text-black bg-white' : 'border-zinc-700 text-zinc-500'}`}>{n}</span>
}

interface Props {
  items: IndexItem[]
  active: string
  onGo: (id: string) => void
  variant: 'rail' | 'bar'
}

/** "Your guide": numbered, clickable index of the page. `rail` = right-hand column, `bar` = compact chips for narrow screens. */
export default function SectionIndex({ items, active, onGo, variant }: Props) {
  const activeTop = items.find((i) => i.id === active || i.children?.some((c) => c.id === active))?.id
  const barRef = useRef<HTMLDivElement>(null)

  // keep the active chip in view in the horizontal bar (without scrolling the page itself)
  useEffect(() => {
    const bar = barRef.current
    const chip = bar?.querySelector<HTMLElement>('[aria-current="location"]')
    if (bar && chip) bar.scrollTo({ left: chip.offsetLeft - bar.clientWidth / 2 + chip.clientWidth / 2, behavior: 'smooth' })
  }, [activeTop])

  if (variant === 'bar') {
    return (
      <nav aria-label="Resume guide">
        <div ref={barRef} className="flex gap-2 overflow-x-auto no-scrollbar">
          {items.map((it, i) => {
            const on = it.id === activeTop
            return (
              <button
                key={it.id}
                type="button"
                onClick={() => onGo(it.id)}
                aria-current={on ? 'location' : undefined}
                className={`shrink-0 flex items-center gap-1.5 text-xs rounded-full border px-3 py-1.5 ${
                  on ? 'bg-white text-black border-white font-medium' : 'border-zinc-700 text-zinc-300'
                }`}
              >
                {it.status === 'done' ? <Check size={12} className={on ? '' : 'text-emerald-300'} /> : <span className="opacity-60">{i + 1}</span>}
                {it.label}
                {it.status === 'attention' && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
              </button>
            )
          })}
        </div>
      </nav>
    )
  }

  return (
    <nav aria-label="Resume guide">
      <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-3">Your guide</div>
      <ol>
        {items.map((it, i) => {
          const on = it.id === activeTop
          const last = i === items.length - 1
          return (
            <li
              key={it.id}
              className={`relative pb-2 ${last ? '' : 'before:content-[""] before:absolute before:left-3 before:top-6 before:bottom-0 before:w-px before:bg-zinc-800'}`}
            >
              <button
                type="button"
                onClick={() => onGo(it.id)}
                aria-current={it.id === active ? 'location' : undefined}
                className="flex gap-2.5 w-full text-left group"
              >
                <Marker n={i + 1} status={it.status} current={on} />
                <span className="min-w-0 pt-0.5">
                  <span className={`block text-sm leading-5 ${on ? 'text-white font-medium' : 'text-zinc-400 group-hover:text-zinc-200'}`}>
                    {it.label}
                  </span>
                  {it.badge && <span className={`block text-[11px] leading-4 ${TONE[it.badge.tone]}`}>{it.badge.text}</span>}
                  {on && <span className="block text-[11px] leading-4 text-zinc-500 mt-0.5">{it.hint}</span>}
                </span>
              </button>

              {it.children && (
                <ul className="ml-[34px] mt-1 space-y-0.5">
                  {it.children.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => onGo(c.id)}
                        aria-current={c.id === active ? 'location' : undefined}
                        className={`flex items-center gap-1.5 text-xs py-0.5 border-l pl-2.5 -ml-px ${
                          c.id === active
                            ? 'border-white text-white'
                            : 'border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-600'
                        }`}
                      >
                        {c.label}
                        {c.attention && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" title="Needs your attention" />}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
