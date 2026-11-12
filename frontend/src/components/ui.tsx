import { AlertTriangle, CheckCircle2, Clock, PauseCircle, ShieldCheck, X } from 'lucide-react'
import { useEffect, useId, useRef, type CSSProperties, type ReactNode } from 'react'
import { STATUS_LABELS } from '../lib/format'
import { buttonClass, cn } from '../lib/styles'
import type { AssessmentStatusName } from '../types/api'

// ---------------------------------------------------------------------------
// Badges
// ---------------------------------------------------------------------------

export function Badge({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset',
        className,
      )}
    >
      {children}
    </span>
  )
}

const STATUS_STYLES: Record<AssessmentStatusName, { className: string; icon: ReactNode }> = {
  in_progress: { className: 'bg-sky-50 text-sky-700 ring-sky-200', icon: <Clock aria-hidden className="size-3" /> },
  interrupted: { className: 'bg-amber-50 text-amber-800 ring-amber-200', icon: <PauseCircle aria-hidden className="size-3" /> },
  awaiting_clinician_review: {
    className: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
    icon: <ShieldCheck aria-hidden className="size-3" />,
  },
  reviewed: { className: 'bg-emerald-50 text-emerald-700 ring-emerald-200', icon: <CheckCircle2 aria-hidden className="size-3" /> },
}

const PATIENT_STATUS_LABELS: Record<AssessmentStatusName, string> = {
  in_progress: 'In progress',
  interrupted: 'Paused',
  awaiting_clinician_review: 'Submitted for review',
  reviewed: 'Reviewed',
}

/** `patientFacing` uses friendlier wording than the clinical workflow state. */
export function StatusBadge({ status, patientFacing = false }: { status: AssessmentStatusName | null; patientFacing?: boolean }) {
  if (!status) return null
  const style = STATUS_STYLES[status]
  return (
    <Badge className={style.className}>
      {style.icon}
      {patientFacing ? PATIENT_STATUS_LABELS[status] : STATUS_LABELS[status]}
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
        {detail !== undefined && <span className="tabular-nums text-slate-500">{detail}</span>}
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
      <span aria-hidden className="absolute text-[11px] font-semibold tabular-nums text-ink">
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
    <div role="alert" className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
      <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
      <p className="flex-1">{message}</p>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="rounded p-0.5 hover:bg-rose-100" aria-label="Dismiss error">
          <X aria-hidden className="size-4" />
        </button>
      )}
    </div>
  )
}

export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-10 text-center">
      <div className="rounded-2xl bg-teal-50 p-3 text-brand">{icon}</div>
      <p className="text-base font-semibold text-ink">{title}</p>
      {children && <div className="max-w-sm text-sm text-slate-500">{children}</div>}
    </div>
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
            <div id={descriptionId} className="text-sm text-slate-500">
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
