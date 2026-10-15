import { useCallback, useEffect, useRef, useState } from 'react'

/** The element that actually scrolls (this app scrolls inside <main>, not the window). */
function scrollParent(el: HTMLElement | null): HTMLElement | null {
  for (let p = el?.parentElement ?? null; p; p = p.parentElement) {
    const o = getComputedStyle(p).overflowY
    if (o === 'auto' || o === 'scroll') return p
  }
  return null // window scrolls
}

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/**
 * Which section is the reader on? `ids` must be in page order. The active one is the last section whose top
 * has scrolled past a line near the top of the scroller; at the very bottom the last section wins, because a
 * short final section could otherwise never reach that line.
 */
export function useScrollSpy(ids: string[], offset = 120) {
  const [active, setActive] = useState(ids[0] ?? '')
  const lockUntil = useRef(0)
  const key = ids.join('|')

  useEffect(() => {
    const first = document.getElementById(ids[0])
    if (!first) return
    const parent = scrollParent(first)
    const target: HTMLElement | Window = parent ?? window
    let raf = 0

    const compute = () => {
      raf = 0
      if (Date.now() < lockUntil.current) return // a click is smooth-scrolling; don't fight it
      const rootTop = parent ? parent.getBoundingClientRect().top : 0
      const line = rootTop + offset
      let current = ids[0]
      let lastVisible = ids[0]
      for (const id of ids) {
        const el = document.getElementById(id)
        if (!el || el.getClientRects().length === 0) continue // missing or display:none (e.g. other mobile tab)
        lastVisible = id
        if (el.getBoundingClientRect().top <= line) current = id
      }
      const atBottom = parent
        ? parent.scrollTop > 0 && parent.scrollTop + parent.clientHeight >= parent.scrollHeight - 4
        : window.scrollY > 0 && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4
      setActive(atBottom ? lastVisible : current)
    }
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(compute)
    }

    compute()
    target.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    // sections change height as content loads / the editor grows, which moves everything below
    const ro = new ResizeObserver(onScroll)
    ids.forEach((id) => {
      const el = document.getElementById(id)
      if (el) ro.observe(el)
    })
    return () => {
      target.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      ro.disconnect()
      if (raf) cancelAnimationFrame(raf)
    }
  }, [key, offset]) // eslint-disable-line react-hooks/exhaustive-deps

  /** Smooth-scroll to a section, focus it for keyboard / screen-reader users, and mark it active right away. */
  const goTo = useCallback((id: string, spy = true) => {
    const el = document.getElementById(id)
    if (!el) return
    if (spy) {
      setActive(id)
      lockUntil.current = Date.now() + 900
    }
    el.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' })
    el.focus({ preventScroll: true })
  }, [])

  return { active, goTo }
}
