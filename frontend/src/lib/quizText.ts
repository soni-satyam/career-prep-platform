/** Splits question text into prose and fenced code blocks (```lang ... ```). */
export interface TextPart {
  code: boolean
  text: string
}

export function splitCodeFences(input: string): TextPart[] {
  const text = (input || '').replace(/\r\n/g, '\n')
  const parts: TextPart[] = []
  const fence = /```[a-zA-Z0-9_+#.-]*[ \t]*\n?([\s\S]*?)(```|$)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = fence.exec(text)) !== null) {
    if (m[0].length === 0) {
      fence.lastIndex++
      continue
    }
    const before = text.slice(last, m.index)
    if (before.trim()) parts.push({ code: false, text: before.trim() })
    // an unterminated fence (m[2] === '') is still treated as code, to the end
    const code = m[1].replace(/\n+$/, '')
    if (code.trim()) parts.push({ code: true, text: code })
    last = m.index + m[0].length
  }
  const rest = text.slice(last)
  if (rest.trim()) parts.push({ code: false, text: rest.trim() })
  return parts.length ? parts : [{ code: false, text: text.trim() }]
}
