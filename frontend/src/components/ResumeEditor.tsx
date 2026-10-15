import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, Plus, TriangleAlert, Trash2 } from 'lucide-react'
import type { ResumeEducation, ResumeItem, TailoredResume } from '../lib/api'

const input =
  'w-full bg-[#0c0c0e] border border-zinc-800 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500'
const label = 'block text-xs text-zinc-400 mb-1'

const uid = (p: string) => `${p}_${Math.random().toString(36).slice(2, 8)}`

function Card({ id, title, children, action }: { id: string; title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section id={id} tabIndex={-1} className="bg-[#111113] border border-zinc-800 rounded-xl p-4 scroll-mt-16 xl:scroll-mt-4 outline-none">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  )
}

function IconBtn({ onClick, title, disabled, children }: { onClick: () => void; title: string; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      disabled={disabled}
      className="p-1.5 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-800 disabled:opacity-30 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  )
}

function ItemList({
  id,
  heading,
  items,
  onChange,
  prefix,
  titlePlaceholder,
  contentPlaceholder,
}: {
  id: string
  heading: string
  items: ResumeItem[]
  onChange: (items: ResumeItem[]) => void
  prefix: string
  titlePlaceholder: string
  contentPlaceholder: string
}) {
  const set = (i: number, patch: Partial<ResumeItem>) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)))
  const move = (i: number, d: number) => {
    const a = [...items]
    const [x] = a.splice(i, 1)
    a.splice(i + d, 0, x)
    onChange(a)
  }
  return (
    <Card
      id={id}
      title={heading}
      action={
        <button
          type="button"
          onClick={() => onChange([...items, { id: uid(prefix), title: '', content: '', source_refs: [] }])}
          className="text-xs flex items-center gap-1 text-zinc-300 hover:text-white"
        >
          <Plus size={14} /> Add
        </button>
      }
    >
      {items.length === 0 && <p className="text-xs text-zinc-600">Nothing here. It won’t appear on the resume.</p>}
      <div className="space-y-4">
        {items.map((it, i) => (
          <div key={it.id || i} className="space-y-2 border border-zinc-800 rounded-lg p-3">
            <div className="flex items-center gap-1">
              <input
                className={input}
                placeholder={titlePlaceholder}
                value={it.title}
                onChange={(e) => set(i, { title: e.target.value })}
              />
              <IconBtn title="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                <ArrowUp size={15} />
              </IconBtn>
              <IconBtn title="Move down" disabled={i === items.length - 1} onClick={() => move(i, 1)}>
                <ArrowDown size={15} />
              </IconBtn>
              <IconBtn title="Remove" onClick={() => onChange(items.filter((_, j) => j !== i))}>
                <Trash2 size={15} />
              </IconBtn>
            </div>
            <textarea
              className={`${input} min-h-28 font-mono text-[13px] leading-relaxed`}
              placeholder={contentPlaceholder}
              value={it.content}
              onChange={(e) => set(i, { content: e.target.value })}
            />
          </div>
        ))}
      </div>
    </Card>
  )
}

export default function ResumeEditor({
  resume,
  onChange,
  unverified,
  resetKey,
}: {
  resume: TailoredResume
  onChange: (r: TailoredResume) => void
  unverified: string[]
  resetKey: number // bump to re-sync the skills text box after a revert / save
}) {
  const [skillsText, setSkillsText] = useState(resume.skills.join(', '))
  useEffect(() => setSkillsText(resume.skills.join(', ')), [resetKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const up = (patch: Partial<TailoredResume>) => onChange({ ...resume, ...patch })
  const setProfile = (k: keyof TailoredResume['profile'], v: string) => up({ profile: { ...resume.profile, [k]: v } })
  const setEdu = (i: number, patch: Partial<ResumeEducation>) =>
    up({ education: resume.education.map((e, j) => (j === i ? { ...e, ...patch } : e)) })
  const flagged = new Set(unverified.map((s) => s.toLowerCase()))
  const shownFlagged = resume.skills.filter((s) => flagged.has(s.trim().toLowerCase()))

  return (
    <div className="space-y-4">
      {shownFlagged.length > 0 && (
        <div className="flex gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
          <TriangleAlert className="text-amber-300 shrink-0 mt-0.5" size={18} />
          <div>
            <div className="text-amber-200 font-medium">Check these skills before you send this resume</div>
            <p className="text-amber-100/80 text-xs mt-1">
              They’re not in your original resume. Keep only the ones you can honestly speak to in an interview:
            </p>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {shownFlagged.map((s) => (
                <span key={s} className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-100">
                  {s}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      <Card id="rt-edit-contact" title="Contact">
        <div className="grid sm:grid-cols-2 gap-3">
          {(
            [
              ['name', 'Full name'],
              ['email', 'Email'],
              ['phone', 'Phone'],
              ['city', 'City'],
              ['github', 'GitHub / portfolio'],
            ] as const
          ).map(([k, l]) => (
            <label key={k} className={k === 'github' ? 'sm:col-span-2' : ''}>
              <span className={label}>{l}</span>
              <input className={input} value={resume.profile[k] ?? ''} onChange={(e) => setProfile(k, e.target.value)} />
            </label>
          ))}
        </div>
      </Card>

      <Card id="rt-edit-summary" title="Summary">
        <textarea
          className={`${input} min-h-24`}
          placeholder="2–3 sentences aimed at this role"
          value={resume.summary}
          onChange={(e) => up({ summary: e.target.value })}
        />
      </Card>

      <Card id="rt-edit-skills" title="Skills">
        <textarea
          className={`${input} min-h-20`}
          placeholder="Comma separated, most relevant first"
          value={skillsText}
          onChange={(e) => {
            setSkillsText(e.target.value)
            up({ skills: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })
          }}
        />
        {resume.skills.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {resume.skills.map((s, i) => (
              <span
                key={`${s}-${i}`}
                title={flagged.has(s.toLowerCase()) ? 'Not found in your original resume' : undefined}
                className={`text-[11px] px-1.5 py-0.5 rounded ${
                  flagged.has(s.toLowerCase()) ? 'bg-amber-500/20 text-amber-200' : 'bg-zinc-800 text-zinc-300'
                }`}
              >
                {s}
              </span>
            ))}
          </div>
        )}
      </Card>

      <ItemList
        id="rt-edit-experience"
        heading="Experience"
        prefix="exp"
        items={resume.experience}
        onChange={(experience) => up({ experience })}
        titlePlaceholder="Role @ Company (dates)"
        contentPlaceholder={'- Built X that did Y, improving Z by N%\n- ...'}
      />
      <ItemList
        id="rt-edit-projects"
        heading="Projects"
        prefix="proj"
        items={resume.projects}
        onChange={(projects) => up({ projects })}
        titlePlaceholder="Project name"
        contentPlaceholder={'- What you built, with which tools, and the result'}
      />

      <Card
        id="rt-edit-education"
        title="Education"
        action={
          <button
            type="button"
            onClick={() =>
              up({ education: [...resume.education, { id: uid('edu'), school: '', degree: '', major: '', start_date: '', end_date: '' }] })
            }
            className="text-xs flex items-center gap-1 text-zinc-300 hover:text-white"
          >
            <Plus size={14} /> Add
          </button>
        }
      >
        <div className="space-y-3">
          {resume.education.map((e, i) => (
            <div key={e.id || i} className="grid grid-cols-2 gap-2 border border-zinc-800 rounded-lg p-3">
              <input className={`${input} col-span-2`} placeholder="School" value={e.school} onChange={(ev) => setEdu(i, { school: ev.target.value })} />
              <input className={input} placeholder="Degree (B.Tech)" value={e.degree} onChange={(ev) => setEdu(i, { degree: ev.target.value })} />
              <input className={input} placeholder="Major" value={e.major} onChange={(ev) => setEdu(i, { major: ev.target.value })} />
              <input className={input} placeholder="Start" value={e.start_date} onChange={(ev) => setEdu(i, { start_date: ev.target.value })} />
              <div className="flex gap-1">
                <input className={input} placeholder="End" value={e.end_date} onChange={(ev) => setEdu(i, { end_date: ev.target.value })} />
                <IconBtn title="Remove" onClick={() => up({ education: resume.education.filter((_, j) => j !== i) })}>
                  <Trash2 size={15} />
                </IconBtn>
              </div>
            </div>
          ))}
          {resume.education.length === 0 && <p className="text-xs text-zinc-600">Nothing here. It won’t appear on the resume.</p>}
        </div>
      </Card>

      <ItemList
        id="rt-edit-awards"
        heading="Awards"
        prefix="award"
        items={resume.awards}
        onChange={(awards) => up({ awards })}
        titlePlaceholder="Award or achievement"
        contentPlaceholder="Optional details"
      />
    </div>
  )
}
