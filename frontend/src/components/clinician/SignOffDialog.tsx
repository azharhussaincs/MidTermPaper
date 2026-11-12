import { CheckCircle2, Flag, Loader2 } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { api, errorMessage } from '../../api/client'
import { buttonClass, cn } from '../../lib/styles'
import type { AssessmentSummaryOutput } from '../../types/api'
import { ErrorNotice, Modal } from '../ui'

export type Decision = 'approve' | 'follow_up'

interface SignOffDialogProps {
  open: boolean
  decision: Decision
  onDecisionChange: (decision: Decision) => void
  onClose: () => void
  sessionId: string
  alias: string
  summary: AssessmentSummaryOutput
  /** Edited "summary of reported concerns", or null to keep the AI draft. */
  editedConcerns: string | null
  notes: string
  onNotesChange: (notes: string) => void
  onSubmitted: () => Promise<void>
}

/**
 * Sign-off form in a light-dismiss modal. Notes live in the parent, so closing the dialog
 * by accident never loses what the clinician typed.
 */
export function SignOffDialog(props: SignOffDialogProps) {
  const { open, decision, onDecisionChange, onClose, sessionId, alias, summary, editedConcerns, notes, onNotesChange, onSubmitted } = props
  const notesId = useId()
  const notesErrorId = useId()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.clinician.review(sessionId, {
        approved: decision === 'approve',
        clinician_notes: notes.trim(),
        revised_summary: editedConcerns ? { ...summary, reported_concerns_summary: editedConcerns } : null,
      })
      onNotesChange('')
      await onSubmitted()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Sign off intake · ${alias}`}
      description="Your decision and notes are saved to the record and resume the paused assessment."
      widthClass="w-[min(34rem,calc(100vw-2rem))]"
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <fieldset className="grid gap-2 sm:grid-cols-2">
          <legend className="sr-only">Decision</legend>
          <DecisionOption
            checked={decision === 'approve'}
            onChange={() => onDecisionChange('approve')}
            icon={<CheckCircle2 aria-hidden className="size-4 text-emerald-600" />}
            title="Approve & sign off"
            hint="Summary is accurate; routine pathway."
          />
          <DecisionOption
            checked={decision === 'follow_up'}
            onChange={() => onDecisionChange('follow_up')}
            icon={<Flag aria-hidden className="size-4 text-rose-600" />}
            title="Request follow-up"
            hint="Needs contact, clarification or escalation."
          />
        </fieldset>

        <div className="space-y-1.5">
          <label htmlFor={notesId} className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Clinician notes <span className="text-rose-600">*</span>
          </label>
          <textarea
            id={notesId}
            value={notes}
            onChange={(e) => onNotesChange(e.target.value)}
            required
            autoFocus
            maxLength={10_000}
            rows={5}
            aria-describedby={notesErrorId}
            placeholder="Clinical observations, contact made, follow-up plan…"
            className="peer w-full rounded-xl border border-line px-3 py-2.5 text-sm focus:border-accent focus:outline-none focus:ring-4 focus:ring-indigo-50 user-invalid:border-rose-400"
          />
          {/* Shown only after interaction (:user-invalid), never on first open. */}
          <p id={notesErrorId} className="hidden text-xs text-rose-700 peer-user-invalid:block">
            Notes are required before signing off.
          </p>
        </div>

        {editedConcerns && (
          <p className="rounded-xl bg-indigo-50 px-3 py-2 text-xs text-indigo-800">
            Your edited summary will replace the AI draft. The non-diagnostic notice is kept automatically.
          </p>
        )}
        {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}

        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <button type="button" onClick={onClose} className={buttonClass('secondary')}>
            Cancel
          </button>
          <button type="submit" disabled={busy} className={buttonClass(decision === 'approve' ? 'primary' : 'accent')}>
            {busy && <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />}
            {decision === 'approve' ? 'Approve & sign off' : 'Request follow-up'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

interface DecisionOptionProps {
  checked: boolean
  onChange: () => void
  icon: React.ReactNode
  title: string
  hint: string
}

function DecisionOption({ checked, onChange, icon, title, hint }: DecisionOptionProps) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 transition-colors',
        checked ? 'border-indigo-300 bg-indigo-50/50 ring-4 ring-indigo-50' : 'border-line hover:bg-slate-50',
      )}
    >
      <input type="radio" name="decision" checked={checked} onChange={onChange} className="mt-0.5 accent-indigo-600" />
      <span>
        <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
          {icon}
          {title}
        </span>
        <span className="text-xs text-slate-500">{hint}</span>
      </span>
    </label>
  )
}
