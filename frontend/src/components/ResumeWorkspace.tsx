import { useEffect, useMemo, useState } from 'react'
import { Check } from 'lucide-react'
import {
  prepApi,
  type ApprovalResult,
  type AtsMatch,
  type ReadinessVerdict,
  type ResumeTemplate,
  type TailoredResume,
} from '../lib/api'
import ApproveAndDownload from './ApproveAndDownload'
import AtsMatchMeter from './AtsMatchMeter'
import ReadinessPanel from './ReadinessPanel'
import ResumeEditor from './ResumeEditor'
import ResumePreview from './ResumePreview'
import SectionIndex, { type IndexItem } from './SectionIndex'
import { useScrollSpy } from '../lib/useScrollSpy'

const EMPTY: TailoredResume = {
  profile: { name: '', email: '', phone: '', city: '', school: '', github: '' },
  summary: '', skills: [], experience: [], projects: [], education: [], awards: [],
}
const normalize = (r: Partial<TailoredResume> | null | undefined): TailoredResume => ({
  ...EMPTY,
  ...(r ?? {}),
  profile: { ...EMPTY.profile, ...(r?.profile ?? {}) },
})

function Steps({ stage }: { stage: 2 | 3 }) {
  const steps = ['Analyzed', 'Review & edit', 'Approve & download']
  return (
    <ol className="flex items-center gap-2 text-xs flex-wrap">
      {steps.map((s, i) => {
        const n = i + 1
        const done = n < stage || (n === 3 && stage === 3)
        const active = n === stage && !done
        return (
          <li key={s} className="flex items-center gap-2">
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center border text-[11px] ${
                done ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300'
                : active ? 'border-white text-white' : 'border-zinc-700 text-zinc-500'
              }`}
            >
              {done ? <Check size={13} /> : n}
            </span>
            <span className={active || done ? 'text-zinc-200' : 'text-zinc-500'}>{s}</span>
            {n < 3 && <span className="w-6 h-px bg-zinc-700" />}
          </li>
        )
      })}
    </ol>
  )
}

export default function ResumeWorkspace({ session, tips }: { session: any; tips?: string[] }) {
  const plan = session.plan || {}
  const initial = useMemo(() => normalize(session.tailored_resume), [session.tailored_resume])

  const [saved, setSaved] = useState<TailoredResume>(initial)
  const [draft, setDraft] = useState<TailoredResume>(initial)
  const [match, setMatch] = useState<AtsMatch | null>(plan.ats_match ?? null)
  const [readiness, setReadiness] = useState<ReadinessVerdict | null>(plan.readiness ?? null)
  const [unverified, setUnverified] = useState<string[]>(plan.unverified_skills ?? [])
  const [templates, setTemplates] = useState<ResumeTemplate[]>([])
  const [template, setTemplate] = useState<string>(plan.resume_approval?.template ?? 'ats_classic')
  const [page, setPage] = useState<string>(plan.resume_approval?.page ?? 'a4')
  const [approval, setApproval] = useState<ApprovalResult | null>(null)
  const [approvedEarlier, setApprovedEarlier] = useState(!!plan.resume_approval)
  const [saving, setSaving] = useState(false)
  const [approving, setApproving] = useState(false)
  const [error, setError] = useState('')
  const [resetKey, setResetKey] = useState(0)
  const [tab, setTab] = useState<'edit' | 'preview'>('edit')
  const [zoom, setZoom] = useState(false)

  useEffect(() => {
    if (!zoom) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setZoom(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [zoom])

  useEffect(() => {
    prepApi.resumeTemplates().then((r) => setTemplates(r.templates)).catch(() => {})
  }, [])

  const dirty = JSON.stringify(draft) !== JSON.stringify(saved)
  const style = templates.find((t) => t.key === template)?.style
  const approved = !!approval?.approved && !dirty

  const save = async (): Promise<boolean> => {
    setSaving(true)
    setError('')
    try {
      const r = await prepApi.saveResume(session.id, draft)
      const next = normalize(r.tailored_resume)
      setSaved(next)
      setDraft(next)
      setMatch(r.ats_match)
      setReadiness(r.readiness)
      setUnverified(r.unverified_skills)
      setApproval(null)
      setApprovedEarlier(false)
      setResetKey((k) => k + 1)
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your edits')
      return false
    } finally {
      setSaving(false)
    }
  }

  const approve = async () => {
    setApproving(true)
    setError('')
    try {
      if (dirty && !(await save())) return
      setApproval(await prepApi.approveResume(session.id, template, page))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not generate the files')
    } finally {
      setApproving(false)
    }
  }

  const revert = () => {
    setDraft(saved)
    setResetKey((k) => k + 1)
  }

  // ---- guide / index -------------------------------------------------------------------------------
  const tplLabel = templates.find((t) => t.key === template)?.label ?? ''
  const flaggedShown = draft.skills.filter((sk) => unverified.some((u) => u.toLowerCase() === sk.trim().toLowerCase())).length
  const hasTips = !!tips && tips.length > 0
  const items: IndexItem[] = [
    ...(match
      ? [{
          id: 'rt-match', label: 'Match score', hint: 'How much of the job your resume covers.',
          badge: { text: match.before ? `${match.before.score}% → ${match.after.score}%` : `${match.after.score}%`, tone: match.after.score >= 75 ? 'good' : match.after.score >= 50 ? 'ok' : 'bad' },
        } as IndexItem]
      : []),
    {
      id: 'rt-readiness', label: 'Readiness', hint: 'What is strong, and what to fix first.',
      badge: readiness ? { text: readiness.label, tone: readiness.level === 'ready' ? 'good' : readiness.level === 'significant_gap' ? 'bad' : 'ok' } : undefined,
    },
    { id: 'rt-template', label: 'Template', hint: 'Pick an ATS-safe look and page size.', badge: tplLabel ? { text: tplLabel, tone: 'muted' } : undefined },
    {
      id: 'rt-edit', label: 'Edit resume', hint: 'Fix wording and remove anything untrue.',
      status: dirty || flaggedShown > 0 ? 'attention' : undefined,
      badge: dirty ? { text: 'Unsaved changes', tone: 'ok' } : flaggedShown > 0 ? { text: `${flaggedShown} skill${flaggedShown > 1 ? 's' : ''} to check`, tone: 'ok' } : undefined,
      children: [
        { id: 'rt-edit-contact', label: 'Contact' },
        { id: 'rt-edit-summary', label: 'Summary' },
        { id: 'rt-edit-skills', label: 'Skills', attention: flaggedShown > 0 },
        { id: 'rt-edit-experience', label: 'Experience' },
        { id: 'rt-edit-projects', label: 'Projects' },
        { id: 'rt-edit-education', label: 'Education' },
        { id: 'rt-edit-awards', label: 'Awards' },
      ],
    },
    { id: 'rt-preview', label: 'Preview', hint: 'See what the recruiter will get.' },
    {
      id: 'rt-approve', label: 'Approve & download', hint: 'Generate and check the PDF and Word files.',
      status: approved ? 'done' : undefined, badge: approved ? { text: 'Approved', tone: 'good' } : undefined,
    },
    ...(hasTips ? [{ id: 'rt-tips', label: 'Resume tips', hint: 'Quick wins before you apply.' } as IndexItem] : []),
  ]
  // preview sits beside the editor, so it is a jump target but not part of the "where am I" tracking
  const spyIds = items.flatMap((i) => (i.id === 'rt-preview' ? [] : [i.id, ...(i.children?.map((c) => c.id) ?? [])]))
  const { active, goTo } = useScrollSpy(spyIds)
  const go = (id: string) => {
    // on narrow screens editor and preview are tabs: make sure the target is the visible one first
    if (id.startsWith('rt-edit')) setTab('edit')
    if (id === 'rt-preview') setTab('preview')
    requestAnimationFrame(() => goTo(id, id !== 'rt-preview'))
  }

  return (
    <div className="xl:grid xl:grid-cols-[minmax(0,1fr)_12rem] xl:gap-8 items-start">
    <div className="space-y-6 min-w-0">
      <Steps stage={approved ? 3 : 2} />
      {/* sticky must sit on a direct child of the tall column, or it cannot travel with the page */}
      <div className="xl:hidden sticky top-0 z-20 -mx-4 sm:-mx-8 px-4 sm:px-8 py-2 bg-[#0a0a0b]/90 backdrop-blur border-b border-zinc-800">
        <SectionIndex variant="bar" items={items} active={active} onGo={go} />
      </div>

      {error && (
        <div className="p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-sm">{error}</div>
      )}

      {match && (
        <div id="rt-match" tabIndex={-1} className="scroll-mt-16 xl:scroll-mt-4 outline-none">
          <AtsMatchMeter match={match} />
        </div>
      )}
      <div id="rt-readiness" tabIndex={-1} className="scroll-mt-16 xl:scroll-mt-4 outline-none">
        <ReadinessPanel readiness={readiness} analysis={session.gap_analysis ?? null} />
      </div>

      {/* template */}
      <section id="rt-template" tabIndex={-1} className="bg-[#111113] border border-zinc-800 rounded-xl p-5 sm:p-6 scroll-mt-16 xl:scroll-mt-4 outline-none">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
          <div>
            <h2 className="font-medium">Template</h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              All templates are single-column with real text and standard headings, so applicant tracking systems can read them.
            </p>
          </div>
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            Page size
            <select
              value={page}
              onChange={(e) => setPage(e.target.value)}
              className="bg-[#0c0c0e] border border-zinc-800 rounded-md px-2 py-1.5 text-sm text-white"
            >
              <option value="a4">A4</option>
              <option value="letter">US Letter</option>
            </select>
          </label>
        </div>
        <div role="radiogroup" aria-label="Resume template" className="grid gap-3 sm:grid-cols-3">
          {templates.map((t) => {
            const on = template === t.key
            return (
              <button
                key={t.key}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => setTemplate(t.key)}
                className={`text-left rounded-lg border p-3 transition ${on ? 'border-white bg-zinc-900' : 'border-zinc-800 hover:border-zinc-600'}`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{t.label}</span>
                  {t.key === 'ats_classic' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">Recommended</span>
                  )}
                </div>
                <p className="text-xs text-zinc-500 mt-1">{t.description}</p>
              </button>
            )
          })}
        </div>
      </section>

      {/* edit + preview */}
      <section id="rt-edit" tabIndex={-1} className="scroll-mt-16 xl:scroll-mt-4 outline-none">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
          <div>
            <h2 className="font-medium">Review &amp; edit your resume</h2>
            <p className="text-xs text-zinc-500 mt-0.5">Edit anything. The preview updates as you type; match and readiness update when you save.</p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className={dirty ? 'text-amber-300' : 'text-zinc-500'}>{dirty ? 'Unsaved changes' : 'All changes saved'}</span>
            <button
              type="button"
              onClick={revert}
              disabled={!dirty || saving}
              className="border border-zinc-700 rounded-md px-3 py-1.5 hover:border-zinc-500 disabled:opacity-40"
            >
              Revert
            </button>
            <button
              type="button"
              onClick={save}
              disabled={!dirty || saving}
              className="bg-white text-black font-medium rounded-md px-3 py-1.5 disabled:opacity-40"
            >
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </div>

        <div className="lg:hidden flex gap-1 mb-3 p-1 bg-zinc-900 rounded-lg w-fit">
          {(['edit', 'preview'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 text-sm rounded-md capitalize ${tab === t ? 'bg-white text-black' : 'text-zinc-400'}`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="grid lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] gap-6 items-start">
          <div className={`${tab === 'edit' ? 'block' : 'hidden'} lg:block`}>
            <ResumeEditor resume={draft} onChange={setDraft} unverified={unverified} resetKey={resetKey} />
          </div>
          <div id="rt-preview" tabIndex={-1} className={`${tab === 'preview' ? 'block' : 'hidden'} lg:block lg:sticky lg:top-4 scroll-mt-16 xl:scroll-mt-4 outline-none`}>
            <ResumePreview resume={draft} style={style} page={page} />
            <button
              type="button"
              onClick={() => setZoom(true)}
              className="mt-3 text-xs border border-zinc-700 rounded-md px-3 py-1.5 hover:border-zinc-500"
            >
              Open full-size preview
            </button>
          </div>
        </div>
      </section>

      {zoom && (
        <div
          className="fixed inset-0 z-50 bg-black/85 overflow-auto p-4 sm:p-8"
          role="dialog"
          aria-modal="true"
          aria-label="Full-size resume preview"
          onClick={() => setZoom(false)}
        >
          <div className="max-w-[860px] mx-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-end mb-3">
              <button
                type="button"
                autoFocus
                onClick={() => setZoom(false)}
                className="bg-white text-black text-sm font-medium px-4 py-1.5 rounded-md"
              >
                Close
              </button>
            </div>
            <ResumePreview resume={draft} style={style} page={page} />
          </div>
        </div>
      )}

      <div id="rt-approve" tabIndex={-1} className="scroll-mt-16 xl:scroll-mt-4 outline-none">
        <ApproveAndDownload
          sessionId={session.id}
          dirty={dirty}
          busy={approving || saving}
          result={approved || (approval && !dirty) ? approval : null}
          approvedEarlier={approvedEarlier}
          onApprove={approve}
        />
      </div>

      {hasTips && (
        <section id="rt-tips" tabIndex={-1} className="bg-[#111113] border border-zinc-800 rounded-xl p-5 scroll-mt-16 xl:scroll-mt-4 outline-none">
          <h2 className="font-medium mb-3">Resume tips</h2>
          <ul className="space-y-2 text-sm text-zinc-300 list-disc list-inside">
            {tips!.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </section>
      )}
    </div>

    <div className="hidden xl:block sticky top-4 self-start">
      <SectionIndex variant="rail" items={items} active={active} onGo={go} />
    </div>
    </div>
  )
}
