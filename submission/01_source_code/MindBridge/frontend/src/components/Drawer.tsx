import { useCallback, useEffect, useRef, type ReactNode } from 'react'

interface DrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  label: string
  children: ReactNode
}

/**
 * Left-edge drawer: a modal <dialog> (inert page, Esc, focus return) containing a horizontal
 * scroll-snap track [sheet | spacer], so swiping, tapping the backdrop, Esc and the close
 * button all slide it closed. An IntersectionObserver on the sheet is the single source of
 * truth for when it has fully left, at which point the dialog actually closes.
 */
export function Drawer({ open, onOpenChange, label, children }: DrawerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const scrollerRef = useRef<HTMLDivElement>(null)
  const sheetRef = useRef<HTMLDivElement>(null)
  const onOpenChangeRef = useRef(onOpenChange)

  useEffect(() => {
    onOpenChangeRef.current = onOpenChange
  }, [onOpenChange])

  const slideClosed = useCallback(() => {
    const scroller = scrollerRef.current
    if (scroller) scroller.scrollTo({ left: scroller.offsetWidth, behavior: 'auto' })
  }, [])

  useEffect(() => {
    const dialog = dialogRef.current
    const scroller = scrollerRef.current
    if (!dialog || !scroller) return
    if (open && !dialog.open) {
      dialog.showModal()
      void (async () => {
        if (!CSS.supports('scroll-initial-target', 'nearest')) {
          // Start off-screen so the scroll below animates the sheet in.
          scroller.scrollTo({ left: scroller.offsetWidth, behavior: 'instant' })
          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
        }
        scroller.scrollTo({ left: 0, behavior: 'auto' })
      })()
    } else if (!open && dialog.open) {
      slideClosed()
    }
  }, [open, slideClosed])

  useEffect(() => {
    const dialog = dialogRef.current
    const scroller = scrollerRef.current
    const sheet = sheetRef.current
    if (!dialog || !scroller || !sheet) return

    // innerWidth can read 0 (hidden or resizing frame); 1/0 is an invalid threshold and throws.
    const visible = 1 / Math.max(window.innerWidth, 1)
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries.at(-1)
        if (entry && entry.intersectionRatio < visible && dialog.open) {
          dialog.close()
          onOpenChangeRef.current(false)
        }
      },
      { root: dialog, threshold: [visible, 1] },
    )
    observer.observe(sheet)

    const onClick = (event: MouseEvent) => {
      if (!sheet.contains(event.target as Node)) slideClosed()
    }
    const onCancel = (event: Event) => {
      if (event.cancelable) {
        event.preventDefault()
        slideClosed()
      }
    }
    dialog.addEventListener('click', onClick)
    dialog.addEventListener('cancel', onCancel)

    // Backdrop fade fallback where scroll-driven animations are unsupported.
    const onScroll = () => {
      dialog.style.setProperty('--drawer-backdrop', String(1 - scroller.scrollLeft / sheet.offsetWidth))
    }
    const needsFallback = !CSS.supports('animation-timeline: scroll()')
    if (needsFallback) scroller.addEventListener('scroll', onScroll)

    return () => {
      observer.disconnect()
      dialog.removeEventListener('click', onClick)
      dialog.removeEventListener('cancel', onCancel)
      if (needsFallback) scroller.removeEventListener('scroll', onScroll)
    }
  }, [slideClosed])

  return (
    <dialog ref={dialogRef} className="drawer" aria-label={label}>
      <div ref={scrollerRef} className="drawer-scroller">
        <div ref={sheetRef} className="drawer-sheet border-r border-line bg-card shadow-float">
          {children}
        </div>
      </div>
    </dialog>
  )
}
