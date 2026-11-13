import { ArrowRight, Plus, X } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { api, ApiError, errorMessage } from '../../api/client'
import { timeAgo } from '../../lib/format'
import { buttonClass, cn, EYEBROW, INPUT } from '../../lib/styles'
import type { AssessmentDetail, AssessmentListItem } from '../../types/api'
import { Drawer } from '../Drawer'
import { ErrorNotice, StatusBadge } from '../ui'

interface SessionDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sessions: AssessmentListItem[]
  selectedId: string | null
  onSelect: (id: string) => void
  onCreated: (detail: AssessmentDetail) => void
}

export function SessionDrawer({ open, onOpenChange, sessions, selectedId, onSelect, onCreated }: SessionDrawerProps) {
  const resumable = sessions.filter((s) => s.status === 'in_progress' || s.status === 'interrupted')
  const submitted = sessions.filter((s) => s.status === 'awaiting_clinician_review' || s.status === 'reviewed')

  return (
    <Drawer open={open} onOpenChange={onOpenChange} label="Switch or resume session">
      <div className="flex min-h-full flex-col">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-ink">Your check-ins</h2>
            <p className="text-sm text-muted">Start a new one or continue where you left off.</p>
          </div>
          <button type="button" autoFocus onClick={() => onOpenChange(false)} className={buttonClass('ghost', 'sm')} aria-label="Close sessions">
            <X aria-hidden className="size-4" />
          </button>
        </div>

        <div className="space-y-6 px-5 py-5">
          <NewSessionForm
            onCreated={(detail) => {
              onCreated(detail)
              onOpenChange(false)
            }}
          />
          <SessionGroup title="Continue" empty="No sessions in progress." items={resumable} selectedId={selectedId} onSelect={(id) => { onSelect(id); onOpenChange(false) }} />
          <SessionGroup title="Submitted" empty="Nothing submitted yet." items={submitted} selectedId={selectedId} onSelect={(id) => { onSelect(id); onOpenChange(false) }} />
        </div>
      </div>
    </Drawer>
  )
}

const ALIAS_RULE = 'Please use an anonymous code with at least one number, such as anon-417 or blue-28, not your name.'

function isAnonymousCode(value: string): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9_-]{2,31}$/.test(value) && /\d/.test(value)
}

export function NewSessionForm({ onCreated, prominent = false }: { onCreated: (detail: AssessmentDetail) => void; prominent?: boolean }) {
  const aliasId = useId()
  const hintId = useId()
  const [alias, setAlias] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const code = alias.trim()
    // Same rule as the backend (schemas/sessions.py); checked here so a name is never sent at all.
    if (code && !isAnonymousCode(code)) {
      setError(ALIAS_RULE)
      return
    }
    setBusy(true)
    setError(null)
    try {
      onCreated(await api.assessments.start({ patient_alias: code || null }))
      setAlias('')
    } catch (err) {
      setError(err instanceof ApiError && err.fieldErrors.length ? err.fieldErrors.map((e) => e.message.replace(/^Value error, /, '')).join(' ') : errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-2">
      <label htmlFor={aliasId} className={EYEBROW}>
        Nickname or code <span className="font-normal normal-case tracking-normal text-slate-400">(optional)</span>
      </label>
      <div className={cn('flex gap-2', prominent && 'flex-col')}>
        <input
          id={aliasId}
          value={alias}
          onChange={(e) => {
            setAlias(e.target.value)
            setError(null)
          }}
          maxLength={32}
          aria-invalid={error === ALIAS_RULE || undefined}
          placeholder="e.g. anon-417"
          aria-describedby={hintId}
          autoComplete="off"
          className={cn(INPUT, prominent ? 'h-12' : 'h-10 flex-1', 'min-w-0')}
        />
        <button type="submit" disabled={busy} className={buttonClass('primary', prominent ? 'lg' : 'md')}>
          {prominent ? (
            <>
              Start check-in <ArrowRight aria-hidden className="size-4" />
            </>
          ) : (
            <>
              <Plus aria-hidden className="size-4" /> New
            </>
          )}
        </button>
      </div>
      <p id={hintId} className="text-xs leading-relaxed text-muted">
        Not your name. This anonymous code is how you find your check-in again, and it is what the clinician sees instead of your
        identity. Use letters and at least one number (e.g. <span className="font-medium text-ink">blue-28</span>), or leave it blank and
        we&apos;ll create one for you.
      </p>
      {error && <ErrorNotice message={error} />}
    </form>
  )
}

interface SessionGroupProps {
  title: string
  empty: string
  items: AssessmentListItem[]
  selectedId: string | null
  onSelect: (id: string) => void
}

function SessionGroup({ title, empty, items, selectedId, onSelect }: SessionGroupProps) {
  return (
    <section className="space-y-2">
      <h3 className={EYEBROW}>
        {title} {items.length > 0 && <span className="font-normal">({items.length})</span>}
      </h3>
      {items.length === 0 ? (
        <p className="text-sm text-slate-400">{empty}</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item) => (
            <li key={item.session_id}>
              <button
                type="button"
                onClick={() => onSelect(item.session_id)}
                aria-current={item.session_id === selectedId ? 'true' : undefined}
                className={cn(
                  'flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors',
                  'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand',
                  item.session_id === selectedId ? 'border-teal-300 bg-teal-50/60' : 'border-line bg-white hover:bg-slate-50',
                )}
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600 uppercase">
                  {(item.patient_alias ?? 'an').replace(/^(anon|demo)-/, '').slice(0, 2)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink">{item.patient_alias ?? 'anonymous'}</span>
                  <span className="flex items-center gap-2 text-xs text-muted">
                    <StatusBadge status={item.status} urgent={item.urgent} />
                    {timeAgo(item.updated_at)}
                  </span>
                </span>
                <span className="text-xs font-semibold tabular-nums text-muted">{Math.round(item.completion_pct)}%</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
