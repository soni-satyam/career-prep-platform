import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { TailoredResume, TemplateStyle } from '../lib/api'

const PT = 96 / 72 // CSS px per point
const MM = 96 / 25.4 // CSS px per millimetre
const PAGES: Record<string, { w: number; h: number }> = {
  a4: { w: 210 * MM, h: 297 * MM },
  letter: { w: 215.9 * MM, h: 279.4 * MM },
}

const FALLBACK: TemplateStyle = {
  font: 'Helvetica', bold: 'Helvetica-Bold', body: 10, name_size: 20, head_size: 10.5,
  leading: 13.2, margin_mm: 18, section_gap: 10, rule: true,
  align: 'left', accent: '#000000', head_bar: false, bar_color: '#EEF1F5',
}

const BULLET = /^\s*(?:[-*•▪◦●–—]|\d+[.)])\s+/

function Lines({ text }: { text: string }) {
  const lines = (text || '').split('\n').filter((l) => l.trim())
  return (
    <>
      {lines.map((l, i) =>
        BULLET.test(l) ? (
          <div key={i} style={{ display: 'flex', gap: 6 * PT, paddingLeft: 2 * PT, marginBottom: 1 * PT }}>
            <span>•</span>
            <span style={{ flex: 1 }}>{l.replace(BULLET, '')}</span>
          </div>
        ) : (
          <div key={i}>{l.trim()}</div>
        )
      )}
    </>
  )
}

/**
 * Paper preview of the resume in the selected template. Uses the same size / margin / font numbers the PDF
 * is generated with, scaled to fit the available width. Page breaks are approximate (dashed lines).
 */
export default function ResumePreview({
  resume,
  style,
  page = 'a4',
}: {
  resume: TailoredResume
  style?: TemplateStyle
  page?: string
}) {
  const s = style ?? FALLBACK
  const dim = PAGES[page] ?? PAGES.a4
  const wrapRef = useRef<HTMLDivElement>(null)
  const paperRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)
  const [height, setHeight] = useState(dim.h)

  useLayoutEffect(() => {
    const fit = () => {
      const w = wrapRef.current?.clientWidth ?? dim.w
      setScale(Math.min(1, w / dim.w))
    }
    fit()
    const ro = new ResizeObserver(fit)
    if (wrapRef.current) ro.observe(wrapRef.current)
    return () => ro.disconnect()
  }, [dim.w])

  useEffect(() => {
    const el = paperRef.current
    if (!el) return
    const measure = () => setHeight(el.offsetHeight)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const serif = s.font.startsWith('Times')
  const family = serif ? "'Times New Roman', Times, serif" : 'Helvetica, Arial, sans-serif'
  const m = s.margin_mm * MM
  const usable = dim.h - 2 * (s.margin_mm * 0.9 * MM)
  const pages = Math.max(1, Math.ceil((height - 2 * (s.margin_mm * 0.9 * MM)) / usable - 0.02))

  const p = resume.profile
  const contact = [p.email, p.phone, p.city, p.github].filter((x) => x && x.trim()).join('  |  ')
  const skills = resume.skills.filter((x) => x.trim())

  const Head = ({ children }: { children: string }) => (
    <div style={{ marginTop: (s.section_gap + (s.head_bar ? 3 : 0)) * PT }}>
      <div
        style={{
          fontWeight: 700,
          fontSize: s.head_size * PT,
          lineHeight: 1.25,
          textTransform: 'uppercase',
          color: s.accent,
          ...(s.head_bar
            ? { background: s.bar_color, padding: `${2 * PT}px ${3 * PT}px`, marginBottom: 5 * PT }
            : {}),
        }}
      >
        {children}
      </div>
      {s.rule && !s.head_bar && (
        <div style={{ borderBottom: `${0.6 * PT}px solid #000`, margin: `${1 * PT}px 0 ${3 * PT}px` }} />
      )}
    </div>
  )

  const Entries = ({ items }: { items: Array<{ title: string; content: string }> }) => (
    <>
      {items
        .filter((it) => it.title.trim() || it.content.trim())
        .map((it, i) => (
          <div key={i} style={{ marginBottom: 3 * PT }}>
            {it.title.trim() && (
              <div style={{ fontWeight: 700, fontSize: (s.body + 0.5) * PT, marginTop: 4 * PT }}>{it.title}</div>
            )}
            <Lines text={it.content} />
          </div>
        ))}
    </>
  )

  const hasItems = (a: Array<{ title: string; content: string }>) => a.some((x) => x.title.trim() || x.content.trim())
  const edu = resume.education.filter((e) => e.school || e.degree || e.major)

  return (
    <div>
      <div className="flex items-center justify-between text-xs text-zinc-500 mb-2">
        <span>Live preview · {page === 'a4' ? 'A4' : 'US Letter'}</span>
        <span className={pages > 2 ? 'text-amber-300' : ''}>≈ {pages} page{pages > 1 ? 's' : ''}</span>
      </div>
      <div ref={wrapRef} className="w-full">
        <div style={{ height: height * scale }} className="relative rounded-md shadow-xl shadow-black/40 overflow-hidden bg-white">
          <div
            ref={paperRef}
            style={{
              width: dim.w,
              minHeight: dim.h,
              transform: `scale(${scale})`,
              transformOrigin: 'top left',
              padding: `${m * 0.9}px ${m}px`,
              boxSizing: 'border-box',
              background: '#fff',
              color: '#000',
              fontFamily: family,
              fontSize: s.body * PT,
              lineHeight: `${s.leading * PT}px`,
              position: 'relative',
            }}
          >
            <div style={{ fontWeight: 700, fontSize: s.name_size * PT, lineHeight: 1.2, marginBottom: 2 * PT, color: s.accent, textAlign: s.align }}>
              {p.name?.trim() || 'Your name'}
            </div>
            {contact && (
              <div style={{ color: '#333', fontSize: (s.body - 0.5) * PT, marginBottom: 2 * PT, textAlign: s.align }}>{contact}</div>
            )}

            {resume.summary.trim() && (
              <>
                <Head>Summary</Head>
                <div>{resume.summary}</div>
              </>
            )}
            {skills.length > 0 && (
              <>
                <Head>Skills</Head>
                <div>{skills.join(', ')}</div>
              </>
            )}
            {hasItems(resume.experience) && (
              <>
                <Head>Experience</Head>
                <Entries items={resume.experience} />
              </>
            )}
            {hasItems(resume.projects) && (
              <>
                <Head>Projects</Head>
                <Entries items={resume.projects} />
              </>
            )}
            {edu.length > 0 && (
              <>
                <Head>Education</Head>
                {edu.map((e, i) => (
                  <div key={i}>
                    {e.school && <div style={{ fontWeight: 700, fontSize: (s.body + 0.5) * PT, marginTop: 4 * PT }}>{e.school}</div>}
                    <div style={{ color: '#333', fontSize: (s.body - 0.5) * PT }}>
                      {[[e.degree, e.major].filter(Boolean).join(' '), [e.start_date, e.end_date].filter(Boolean).join(' - ')]
                        .filter(Boolean)
                        .join(', ')}
                    </div>
                  </div>
                ))}
              </>
            )}
            {hasItems(resume.awards) && (
              <>
                <Head>Awards</Head>
                <Entries items={resume.awards} />
              </>
            )}

            {/* approximate page breaks */}
            {Array.from({ length: Math.max(0, pages - 1) }, (_, i) => (
              <div
                key={i}
                style={{ position: 'absolute', left: 0, right: 0, top: dim.h * (i + 1), borderTop: '1px dashed #c4c4c4' }}
              />
            ))}
          </div>
        </div>
      </div>
      <p className="text-[11px] text-zinc-600 mt-2">
        Page breaks are approximate. The exact file is generated and checked when you approve.
      </p>
    </div>
  )
}
