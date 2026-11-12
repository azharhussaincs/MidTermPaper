import { AlertOctagon, CheckCircle2, Flag, Inbox, Info, PencilLine, ShieldAlert, Sparkles, Undo2 } from 'lucide-react'
import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { api, errorMessage } from '../api/client'
import { formatDateTime, formatTime, RISK_LABELS } from '../lib/format'
import { groupRiskFlags, groupSummaryReviewAreas, highestLevel, triagePriority } from '../lib/risk'
import { buttonClass, CARD, cn, RISK_STYLES } from '../lib/styles'
import type { AssessmentDetail, AssessmentSummaryOutput, ClinicianQueueResponse } from '../types/api'
import { Inconsistencies, MissingFields } from './clinician/DataQuality'
import { DomainGrid } from './clinician/DomainGrid'
import { RiskHighlights } from './clinician/RiskHighlights'
import { SignOffDialog, type Decision } from './clinician/SignOffDialog'
import { TriageQueue, type QueueFilter } from './clinician/TriageQueue'
import { Badge, EmptyState, ErrorNotice, ProgressRing, StatusBadge } from './ui'

interface ClinicianWorkspaceProps {
  queue: ClinicianQueueResponse | null
  queueError: unknown
  refreshQueue: () => Promise<unknown>
}

export function ClinicianWorkspace({ queue, queueError, refreshQueue }: ClinicianWorkspaceProps) {
  const [filter, setFilter] = useState<QueueFilter>('awaiting')
  const [chosenId, setChosenId] = useState<string | null>(null)
  const [loadedDetail, setDetail] = useState<AssessmentDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Default to the top of the queue (highest priority) until the clinician picks a case.
  const selectedId = chosenId ?? (filter === 'awaiting' ? (queue?.awaiting_review[0]?.session_id ?? null) : null)
  const detail = loadedDetail?.session_id === selectedId ? loadedDetail : null

  const loadDetail = useCallback(async (id: string, signal?: AbortSignal) => {
    try {
      setDetail(await api.assessments.get(id, signal))
    } catch (err) {
      if (!signal?.aborted) setError(errorMessage(err))
    }
  }, [])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    void loadDetail(selectedId, controller.signal)
    return () => controller.abort()
  }, [selectedId, loadDetail])

  return (
    <div className="h-full lg:grid lg:grid-cols-[320px_minmax(0,1fr)]">
      <TriageQueue
        awaiting={queue?.awaiting_review ?? []}
        reviewed={queue?.recently_reviewed ?? []}
        filter={filter}
        onFilterChange={setFilter}
        selectedId={selectedId}
        onSelect={setChosenId}
        error={queueError ? errorMessage(queueError) : null}
      />

      <main className="min-h-[60dvh] overflow-y-auto lg:min-h-0">
        {error && (
          <div className="mx-auto max-w-6xl px-6 pt-6">
            <ErrorNotice message={error} onDismiss={() => setError(null)} />
          </div>
        )}
        {detail ? (
          <Dossier
            key={detail.session_id}
            detail={detail}
            onReviewed={async () => {
              // Keep the signed-off case on screen; otherwise the default jumps to the next item.
              setChosenId(detail.session_id)
              setFilter('reviewed')
              await Promise.all([loadDetail(detail.session_id), refreshQueue()])
            }}
          />
        ) : (
          <EmptyState icon={<Inbox aria-hidden className="size-6" />} title={selectedId ? 'Loading intake…' : 'Select an intake to review'}>
            Urgent and high-risk cases are listed first in the triage queue.
          </EmptyState>
        )}
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Dossier
// ---------------------------------------------------------------------------

type Tab = 'summary' | 'conversation'

function Dossier({ detail, onReviewed }: { detail: AssessmentDetail; onReviewed: () => Promise<void> }) {
  const pending = detail.pending_review
  const final = detail.final_output
  const summary: AssessmentSummaryOutput | null = final?.summary ?? pending?.summary ?? detail.clinical_summary ?? detail.draft_summary
  const [tab, setTab] = useState<Tab>('summary')
  const [editing, setEditing] = useState(false)
  const [concerns, setConcerns] = useState(summary?.reported_concerns_summary ?? '')
  const [dialog, setDialog] = useState<Decision | null>(null)
  const [decision, setDecision] = useState<Decision>('approve')
  const [notes, setNotes] = useState('')

  if (!summary) {
    return (
      <EmptyState icon={<Inbox aria-hidden className="size-6" />} title="No summary yet">
        This session has not produced a summary for review.
      </EmptyState>
    )
  }

  const alerts = detail.risk_flags.length ? groupRiskFlags(detail.risk_flags) : groupSummaryReviewAreas(summary)
  const riskLevel = highestLevel(detail.risk_flags.map((f) => f.level))
  const urgent = pending?.urgent ?? final?.urgent ?? detail.requires_urgent_escalation
  const priority = triagePriority({ urgent, risk_level: riskLevel })
  const early = pending?.early_submission ?? final?.early_submission ?? false
  const editedConcerns = editing && concerns.trim() && concerns.trim() !== summary.reported_concerns_summary ? concerns.trim() : null

  function openSignOff(next: Decision) {
    setDecision(next)
    setDialog(next)
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 sm:p-6">
      {/* 1. Header card */}
      <header className={cn(CARD, 'overflow-hidden')}>
        {urgent && (
          <p className="flex items-center gap-2 bg-rose-600 px-5 py-2 text-sm font-medium text-white">
            <AlertOctagon aria-hidden className="size-4" />
            Safety-critical disclosure. The screening was paused and crisis resources were shown to the patient.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-4 px-5 py-4">
          <ProgressRing value={summary.completion_status.percentage} label="Completion" size="3.25rem" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <h1 className="truncate text-lg font-semibold tracking-tight text-ink">{detail.patient_alias ?? 'anonymous'}</h1>
            <div className="flex flex-wrap items-center gap-1.5">
              <StatusBadge status={detail.status} />
              <Badge className={RISK_STYLES[riskLevel]}>
                <ShieldAlert aria-hidden className="size-3" />
                Risk: {RISK_LABELS[riskLevel]}
              </Badge>
              <Badge
                className={
                  priority === 'urgent'
                    ? 'bg-rose-50 text-rose-700 ring-rose-200'
                    : priority === 'high'
                      ? 'bg-amber-50 text-amber-800 ring-amber-200'
                      : 'bg-teal-50 text-teal-800 ring-teal-200'
                }
              >
                {priority === 'urgent' ? 'Urgent' : priority === 'high' ? 'High priority' : 'Routine'}
              </Badge>
              {early && <Badge className="bg-slate-50 text-slate-600 ring-slate-200">Submitted early</Badge>}
              {final?.summary_revised_by_clinician && <Badge className="bg-indigo-50 text-indigo-700 ring-indigo-200">Edited by clinician</Badge>}
              <span className="text-xs text-slate-500">Started {formatDateTime(detail.created_at)}</span>
            </div>
          </div>
          {pending ? (
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => openSignOff('follow_up')} className={buttonClass('danger')}>
                <Flag aria-hidden className="size-4" />
                Request follow-up
              </button>
              <button type="button" onClick={() => openSignOff('approve')} className={buttonClass('primary')}>
                <CheckCircle2 aria-hidden className="size-4" />
                Approve &amp; sign off
              </button>
            </div>
          ) : (
            final && (
              <Badge className={final.clinician_approved ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-amber-50 text-amber-800 ring-amber-200'}>
                {final.clinician_approved ? <CheckCircle2 aria-hidden className="size-3" /> : <Flag aria-hidden className="size-3" />}
                {final.clinician_approved ? 'Signed off' : 'Follow-up requested'} · {formatDateTime(final.reviewed_at)}
              </Badge>
            )
          )}
        </div>
        {final?.clinician_notes && (
          <div className="border-t border-line bg-slate-50 px-5 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Clinician notes</p>
            <p className="mt-0.5 whitespace-pre-wrap text-sm text-ink">{final.clinician_notes}</p>
          </div>
        )}
      </header>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { id: 'summary', label: 'Clinical summary' },
          { id: 'conversation', label: 'Conversation', count: detail.messages.filter((m) => m.role === 'user').length },
        ]}
      >
        {tab === 'summary' ? (
          <div className="space-y-5">
            {/* 2. Executive summary & risk highlights */}
            <section aria-labelledby="exec-summary" className={cn(CARD, 'divide-y divide-line')}>
              <div className="space-y-3 p-5">
                <div className="flex items-center justify-between gap-3">
                  <h2 id="exec-summary" className="text-sm font-semibold text-ink">
                    Summary of reported concerns
                  </h2>
                  {pending &&
                    (editing ? (
                      <button
                        type="button"
                        onClick={() => {
                          setConcerns(summary.reported_concerns_summary)
                          setEditing(false)
                        }}
                        className={buttonClass('ghost', 'sm')}
                      >
                        <Undo2 aria-hidden className="size-3.5" />
                        Discard edit
                      </button>
                    ) : (
                      <button type="button" onClick={() => setEditing(true)} className={buttonClass('ghost', 'sm')}>
                        <PencilLine aria-hidden className="size-3.5" />
                        Edit
                      </button>
                    ))}
                </div>
                {editing ? (
                  <textarea
                    aria-label="Edit the summary of reported concerns"
                    value={concerns}
                    onChange={(e) => setConcerns(e.target.value)}
                    rows={5}
                    className="w-full rounded-xl border border-indigo-200 px-3 py-2.5 text-sm leading-relaxed focus:border-accent focus:outline-none focus:ring-4 focus:ring-indigo-50"
                  />
                ) : (
                  <p className="text-[15px] leading-relaxed text-slate-700">{summary.reported_concerns_summary}</p>
                )}
                {pending && !pending.reflection_passed && (
                  <details className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                    <summary className="cursor-pointer font-medium">AI self-check did not fully pass. Read the summary carefully.</summary>
                    <p className="mt-1 whitespace-pre-wrap text-xs">{pending.reflection_feedback}</p>
                  </details>
                )}
              </div>
              <div className="space-y-3 p-5">
                <h2 className="text-sm font-semibold text-ink">Areas requiring professional review</h2>
                <RiskHighlights alerts={alerts} />
              </div>
            </section>

            <Inconsistencies items={detail.inconsistencies} />

            {/* 3. Six-domain structured intake */}
            <section aria-labelledby="structured-intake" className="space-y-3">
              <h2 id="structured-intake" className="text-sm font-semibold text-ink">
                Structured intake <span className="font-normal text-slate-500">· self-reported</span>
              </h2>
              <DomainGrid data={detail.domain_data} progress={detail.domain_completion_map} />
            </section>

            {/* 4. Data quality */}
            <MissingFields fields={detail.missing_fields} />

            {/* 5. Non-diagnostic notice */}
            <footer className="flex items-start gap-3 rounded-2xl border border-line bg-white/60 px-5 py-4 text-xs leading-relaxed text-slate-500">
              <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-slate-400" />
              <p>
                <span className="font-semibold text-slate-700">Non-diagnostic screening. </span>
                {summary.non_diagnostic_disclaimer}
              </p>
            </footer>
          </div>
        ) : (
          <Transcript detail={detail} />
        )}
      </Tabs>

      {pending && (
        <SignOffDialog
          open={dialog !== null}
          decision={decision}
          onDecisionChange={setDecision}
          onClose={() => setDialog(null)}
          sessionId={detail.session_id}
          alias={detail.patient_alias ?? 'anonymous'}
          summary={summary}
          editedConcerns={editedConcerns}
          notes={notes}
          onNotesChange={setNotes}
          onSubmitted={onReviewed}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tabs (WAI-ARIA tabs with roving tabindex; selection follows focus)
// ---------------------------------------------------------------------------

interface TabsProps<T extends string> {
  value: T
  onChange: (value: T) => void
  tabs: { id: T; label: string; count?: number }[]
  children: ReactNode
}

function Tabs<T extends string>({ value, onChange, tabs, children }: TabsProps<T>) {
  const baseId = useId()
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex((t) => t.id === value)
    const next =
      event.key === 'ArrowRight' ? (index + 1) % tabs.length
        : event.key === 'ArrowLeft' ? (index - 1 + tabs.length) % tabs.length
          : event.key === 'Home' ? 0
            : event.key === 'End' ? tabs.length - 1
              : -1  // prettier-ignore
    if (next < 0) return
    event.preventDefault()
    onChange(tabs[next].id)
    refs.current[next]?.focus()
  }

  return (
    <div className="space-y-4">
      <div role="tablist" aria-label="Intake views" onKeyDown={onKeyDown} className="flex gap-6 border-b border-line">
        {tabs.map((tab, i) => {
          const selected = tab.id === value
          return (
            <button
              key={tab.id}
              ref={(el) => {
                refs.current[i] = el
              }}
              type="button"
              role="tab"
              id={`${baseId}-${tab.id}`}
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
              className={cn(
                'relative -mb-px flex items-center gap-1.5 pb-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
                // Underline (shape), not colour alone, marks the selected tab.
                selected ? 'text-ink after:absolute after:inset-x-0 after:bottom-0 after:border-b-2 after:border-accent' : 'text-slate-500 hover:text-ink',
              )}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className="rounded-full bg-slate-100 px-1.5 text-[11px] tabular-nums text-slate-600">{tab.count}</span>
              )}
            </button>
          )
        })}
      </div>
      <div role="tabpanel" aria-labelledby={`${baseId}-${value}`}>
        {children}
      </div>
    </div>
  )
}

function Transcript({ detail }: { detail: AssessmentDetail }) {
  const messages = detail.messages.filter((m) => (m.role === 'user' || m.role === 'assistant') && m.content.trim())
  return (
    <ol className={cn(CARD, 'divide-y divide-line')}>
      {messages.map((m, i) => (
        <li key={m.id ?? i} className="flex gap-3 px-5 py-3.5">
          <span
            aria-hidden
            className={cn(
              'grid size-7 shrink-0 place-items-center rounded-full text-[11px] font-semibold',
              m.role === 'user' ? 'bg-indigo-50 text-accent' : 'bg-teal-50 text-brand',
            )}
          >
            {m.role === 'user' ? 'Pt' : <Sparkles className="size-3.5" />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              {m.role === 'user' ? 'Patient' : 'Intake assistant'}
              {m.created_at && <span className="ml-2 font-normal normal-case tracking-normal">{formatTime(m.created_at)}</span>}
            </p>
            <p className="whitespace-pre-wrap text-sm text-ink">{m.content}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}
