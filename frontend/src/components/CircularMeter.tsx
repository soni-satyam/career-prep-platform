import { useEffect, useState } from 'react'

export function scoreTone(score: number) {
  if (score >= 75) return { stroke: '#10b981', text: 'text-emerald-300', label: 'Strong match' }
  if (score >= 50) return { stroke: '#f59e0b', text: 'text-amber-300', label: 'Moderate match' }
  return { stroke: '#ef4444', text: 'text-red-300', label: 'Weak match' }
}

interface Props {
  value: number // 0-100
  label: string
  size?: number
  stroke?: number
}

/** Ring gauge. The arc animates from empty to the value on mount and whenever the value changes. */
export default function CircularMeter({ value, label, size = 148, stroke = 12 }: Props) {
  const v = Math.max(0, Math.min(100, Math.round(value)))
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(v))
    return () => cancelAnimationFrame(id)
  }, [v])

  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const t = scoreTone(v)
  return (
    <div className="flex flex-col items-center text-center">
      <div
        className="relative"
        style={{ width: size, height: size }}
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={v}
      >
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#27272a" strokeWidth={stroke} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={t.stroke}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - shown / 100)}
            style={{ transition: 'stroke-dashoffset 1s cubic-bezier(.22,1,.36,1), stroke .4s' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-3xl font-semibold tabular-nums leading-none ${t.text}`}>
            {v}
            <span className="text-lg">%</span>
          </span>
          <span className="text-[11px] text-zinc-500 mt-1">{t.label}</span>
        </div>
      </div>
      <div className="text-sm text-zinc-300 mt-3 font-medium">{label}</div>
    </div>
  )
}
