import { useState } from 'react'
import { CheckCircle2, Download, FileText, TriangleAlert, XCircle } from 'lucide-react'
import { prepApi, type ApprovalResult, type FileValidation, type GeneratedFile } from '../lib/api'

function Checklist({ v }: { v: FileValidation }) {
  return (
    <ul className="space-y-1.5">
      {v.checks.map((c) => (
        <li key={c.id} className="flex items-start gap-2 text-xs">
          {c.status === 'pass' && <CheckCircle2 size={15} className="text-emerald-400 shrink-0 mt-px" />}
          {c.status === 'warn' && <TriangleAlert size={15} className="text-amber-400 shrink-0 mt-px" />}
          {c.status === 'fail' && <XCircle size={15} className="text-red-400 shrink-0 mt-px" />}
          <span>
            <span className={c.status === 'fail' ? 'text-red-300' : 'text-zinc-200'}>{c.label}</span>
            {c.detail && <span className="text-zinc-500"> — {c.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}

function FileCard({ title, v, file }: { title: string; v: FileValidation; file?: GeneratedFile }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const download = async () => {
    if (!file) return
    setBusy(true)
    setErr('')
    try {
      await prepApi.downloadByUrl(file.url, file.filename)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Download failed')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="border border-zinc-800 rounded-lg p-4 bg-[#0c0c0e]">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={18} className="text-zinc-400 shrink-0" />
          <div className="min-w-0">
            <div className="text-sm font-medium">{title}</div>
            {file && (
              <div className="text-[11px] text-zinc-500 truncate">
                {file.filename} · {file.size_kb} KB{file.pages ? ` · ${file.pages} page${file.pages > 1 ? 's' : ''}` : ''}
              </div>
            )}
          </div>
        </div>
        {file && (
          <button
            type="button"
            onClick={download}
            disabled={busy}
            className="shrink-0 flex items-center gap-1.5 bg-white text-black text-sm font-medium px-3 py-1.5 rounded-md hover:bg-zinc-200 disabled:opacity-60"
          >
            <Download size={15} /> {busy ? 'Preparing…' : 'Download'}
          </button>
        )}
      </div>
      <Checklist v={v} />
      {err && <div className="text-xs text-red-400 mt-2">{err}</div>}
    </div>
  )
}

export default function ApproveAndDownload({
  sessionId,
  dirty,
  busy,
  result,
  approvedEarlier,
  onApprove,
}: {
  sessionId: number
  dirty: boolean
  busy: boolean
  result: ApprovalResult | null
  approvedEarlier: boolean
  onApprove: () => void
}) {
  const [htmlBusy, setHtmlBusy] = useState(false)
  const approved = !!result?.approved

  return (
    <section className="bg-[#111113] border border-zinc-800 rounded-xl p-5 sm:p-6">
      <h2 className="font-medium">Approve &amp; download</h2>
      <p className="text-xs text-zinc-500 mt-0.5 mb-4">
        Approving saves your edits, generates the PDF and Word files in the selected template, then re-opens each file
        and checks it the way an applicant tracking system would.
      </p>

      {!result && (
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={onApprove}
            disabled={busy}
            className="bg-white text-black text-sm font-medium px-5 py-2.5 rounded-md hover:bg-zinc-200 disabled:opacity-60"
          >
            {busy ? 'Generating & checking files…' : approvedEarlier && !dirty ? 'Get download links' : 'Approve & generate files'}
          </button>
          {dirty && <span className="text-xs text-amber-300">Your unsaved edits will be saved first.</span>}
          {approvedEarlier && !dirty && <span className="text-xs text-emerald-300">✓ You approved this resume earlier.</span>}
        </div>
      )}

      {result && !result.approved && (
        <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          We couldn’t approve this resume — a file failed validation. Fix the items marked ✗ below (usually missing
          content or contact details), then try again.
        </div>
      )}

      {result && (
        <>
          {approved && (
            <div className="mb-4 flex items-center gap-2 text-sm text-emerald-300">
              <CheckCircle2 size={18} /> Approved — both files passed validation.
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            <FileCard title="PDF" v={result.validation.pdf} file={result.files.find((f) => f.format === 'pdf')} />
            <FileCard title="Word (DOCX)" v={result.validation.docx} file={result.files.find((f) => f.format === 'docx')} />
          </div>
          <div className="flex items-center gap-4 mt-4 flex-wrap">
            <button
              type="button"
              onClick={onApprove}
              disabled={busy}
              className="text-xs border border-zinc-700 rounded-md px-3 py-1.5 hover:border-zinc-500 disabled:opacity-60"
            >
              {busy ? 'Working…' : 'Regenerate'}
            </button>
            <button
              type="button"
              disabled={htmlBusy}
              onClick={async () => {
                setHtmlBusy(true)
                try {
                  await prepApi.downloadResumeHtml(sessionId)
                } finally {
                  setHtmlBusy(false)
                }
              }}
              className="text-xs text-zinc-400 underline"
            >
              Also download as HTML
            </button>
          </div>
        </>
      )}
    </section>
  )
}
