import { AlertTriangle, CheckCircle2, Clock, PauseCircle, ShieldCheck, X } from 'lucide-react'
import { useEffect, useId, useRef, type CSSProperties, type ReactNode } from 'react'
import { displayStage, STAGE_LABELS, type DisplayStage } from '../lib/format'
import { buttonClass, CARD, cn } from '../lib/styles'
import type { AssessmentStatusName } from '../types/api'

// ---------------------------------------------------------------------------
// Badges
// ---------------------------------------------------------------------------

export function Badge({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset',
        className,
      )}
    >
      {children}
    </span>
  )
}

const STAGE_STYLES: Record<DisplayStage, { className: string; icon: ReactNode }> = {
  in_progress: { className: 'bg-sky-50 text-sky-700 ring-sky-200', icon: <Clock aria-hidden className="size-3" /> },
  paused: { className: 'bg-amber-50 text-amber-800 ring-amber-200', icon: <PauseCircle aria-hidden className="size-3" /> },
  priority_review: { className: 'bg-rose-50 text-rose-700 ring-rose-200', icon: <AlertTriangle aria-hidden className="size-3" /> },
  submitted: { className: 'bg-teal-50 text-teal-700 ring-teal-200', icon: <ShieldCheck aria-hidden className="size-3" /> },
  reviewed: { className: 'bg-emerald-50 text-emerald-700 ring-emerald-200', icon: <CheckCircle2 aria-hidden className="size-3" /> },
}

/** Workflow status plus urgency, so a safety escalation never reads as a normal submission. */
export function StatusBadge({ status, urgent = false }: { status: AssessmentStatusName | null; urgent?: boolean }) {
  if (!status) return null
  const stage = displayStage(status, urgent)
  const style = STAGE_STYLES[stage]
  return (
    <Badge className={style.className}>
      {style.icon}
      {STAGE_LABELS[stage]}
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Progress
// ---------------------------------------------------------------------------

interface MeterProps {
  label: string
  value: number
  max?: number
  detail?: ReactNode
  tone?: 'warn' | 'danger' | 'complete'
  hideLabel?: boolean
}

export function Meter({ label, value, max = 100, detail, tone, hideLabel = false }: MeterProps) {
  const id = useId()
  return (
    <div className="space-y-1">
      <div className={cn('flex items-baseline justify-between gap-2 text-xs', hideLabel && 'sr-only')}>
        <label htmlFor={id} className="font-medium text-slate-600">
          {label}
        </label>
        {detail !== undefined && <span className="tabular-nums text-muted">{detail}</span>}
      </div>
      <progress id={id} className={cn('meter', tone ?? (value >= max ? 'complete' : undefined))} max={max} value={value} />
    </div>
  )
}

/** Circular progress on a native <progress> (accessible value); the centre % is decorative. */
export function ProgressRing({ value, label, size = '2.75rem' }: { value: number; label: string; size?: string }) {
  const rounded = Math.round(value)
  return (
    <div className="relative grid shrink-0 place-items-center">
      <progress
        className={cn('progress-ring', rounded >= 100 && 'complete')}
        max={100}
        value={rounded}
        aria-label={label}
        style={{ '--value': rounded, '--size': size } as CSSProperties}
      />
      <span aria-hidden className="absolute text-xs font-semibold tabular-nums text-ink">
        {rounded}%
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Feedback
// ---------------------------------------------------------------------------

export function ErrorNotice({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-900">
      <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-rose-600" />
      <p className="flex-1">{message}</p>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="rounded p-0.5 text-rose-700 hover:bg-rose-100" aria-label="Dismiss error">
          <X aria-hidden className="size-4" />
        </button>
      )}
    </div>
  )
}

/** Centred message for "nothing here yet", "choose something" and similar quiet states. */
export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <div className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand">{icon}</div>
      <p className="text-base font-semibold text-ink">{title}</p>
      {children && <div className="max-w-sm text-sm leading-relaxed text-muted">{children}</div>}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cn('skeleton block', className)} />
}

/** Placeholder layout while a page loads; announced once to assistive tech. */
export function LoadingState({ label, variant = 'page' }: { label: string; variant?: 'page' | 'chat' }) {
  return (
    <div role="status" className="mx-auto w-full max-w-5xl space-y-4 p-4 sm:p-6">
      <span className="sr-only">{label}</span>
      {variant === 'chat' ? (
        <div className="mx-auto max-w-2xl space-y-4 pt-6">
          <Skeleton className="h-16 w-3/4" />
          <Skeleton className="ml-auto h-10 w-1/2" />
          <Skeleton className="h-20 w-2/3" />
        </div>
      ) : (
        <>
          <div className={cn(CARD, 'flex items-center gap-4 p-5')}>
            <Skeleton className="size-12 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-72" />
            </div>
          </div>
          <div className={cn(CARD, 'space-y-3 p-5')}>
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <Skeleton className="h-40 rounded-2xl" />
            <Skeleton className="h-40 rounded-2xl" />
            <Skeleton className="h-40 rounded-2xl" />
          </div>
        </>
      )}
    </div>
  )
}

interface SectionCardProps {
  title: string
  icon?: ReactNode
  /** Short context next to the title, e.g. a count. */
  meta?: ReactNode
  /** Right-aligned actions. */
  actions?: ReactNode
  id?: string
  className?: string
  children: ReactNode
}

/** The one card layout every content section uses: icon + title row, then the body. */
export function SectionCard({ title, icon, meta, actions, id, className, children }: SectionCardProps) {
  const headingId = useId()
  return (
    <section id={id} aria-labelledby={headingId} className={cn(CARD, className)}>
      <header className="flex min-h-14 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-line px-5 py-3">
        <h2 id={headingId} className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          {icon && <span className="text-brand [&>svg]:size-4">{icon}</span>}
          {title}
          {meta}
        </h2>
        {actions && <div className="flex items-center gap-1.5">{actions}</div>}
      </header>
      <div className="p-5">{children}</div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Modal dialog (native <dialog>: focus containment, Esc, inert page, focus return)
// ---------------------------------------------------------------------------

interface ModalProps {
  open: boolean
  title: string
  description?: ReactNode
  onClose: () => void
  children: ReactNode
  widthClass?: string
}

/** Light-dismiss via `closedby="any"`, with the click-outside fallback where it is unsupported. */
export function Modal({ open, title, description, onClose, children, widthClass }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  useEffect(() => {
    const dialog = ref.current
    if (!dialog || 'closedBy' in HTMLDialogElement.prototype) return
    const onClick = (event: MouseEvent) => {
      if (event.target !== dialog) return
      const r = dialog.getBoundingClientRect()
      const inside = r.top <= event.clientY && event.clientY <= r.bottom && r.left <= event.clientX && event.clientX <= r.right
      if (!inside) dialog.close()
    }
    dialog.addEventListener('click', onClick)
    return () => dialog.removeEventListener('click', onClick)
  }, [])

  return (
    <dialog
      ref={ref}
      {...({ closedby: 'any' } as Record<string, string>)}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onClose={onClose}
      className={cn(
        'm-auto rounded-2xl border border-line bg-card p-0 text-ink shadow-float',
        widthClass ?? 'w-[min(30rem,calc(100vw-2rem))]',
      )}
    >
      <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
        <div className="space-y-1">
          <h2 id={titleId} className="text-base font-semibold text-ink">
            {title}
          </h2>
          {description && (
            <div id={descriptionId} className="text-sm text-muted">
              {description}
            </div>
          )}
        </div>
        <button type="button" onClick={() => ref.current?.close()} className={buttonClass('ghost', 'sm')} aria-label="Close">
          <X aria-hidden className="size-4" />
        </button>
      </div>
      <div className="px-5 py-4">{children}</div>
    </dialog>
  )
}

interface ConfirmDialogProps {
  open: boolean
  title: string
  children: ReactNode
  confirmLabel: string
  onConfirm: () => void
  onClose: () => void
}

/** Confirmation with the safe action (Cancel) focused first. */
export function ConfirmDialog({ open, title, children, confirmLabel, onConfirm, onClose }: ConfirmDialogProps) {
  return (
    <Modal open={open} title={title} onClose={onClose}>
      <form
        method="dialog"
        onSubmit={(event) => {
          const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null
          if (submitter?.value === 'confirm') onConfirm()
        }}
        className="space-y-4"
      >
        <div className="space-y-2 text-sm text-slate-600">{children}</div>
        <div className="flex justify-end gap-2">
          <button type="submit" value="cancel" autoFocus className={buttonClass('secondary')}>
            Cancel
          </button>
          <button type="submit" value="confirm" className={buttonClass('primary')}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </Modal>
  )
}
