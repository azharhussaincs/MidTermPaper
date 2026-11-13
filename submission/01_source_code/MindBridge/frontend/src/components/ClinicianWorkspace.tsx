import { AlertOctagon, AlertTriangle, CheckCircle2, Flag, Inbox, Info, PencilLine, ShieldCheck, Sparkles, Stethoscope, Undo2, UserRound } from 'lucide-react'
import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { api, errorMessage } from '../api/client'
import { DOMAIN_META } from '../lib/domains'
import { displayStage, formatDateTime, formatTime, humanize, RISK_LABELS, type DisplayStage } from '../lib/format'
import { groupRiskFlags, groupSummaryReviewAreas, highestLevel, triagePriority, type TriagePriority } from '../lib/risk'
import { buttonClass, CARD, cn, EYEBROW, INPUT } from '../lib/styles'
import type { AssessmentDetail, AssessmentDomain, AssessmentDomainData, AssessmentSummaryOutput, ClinicianQueueResponse } from '../types/api'
import { Inconsistencies, MissingFields } from './clinician/DataQuality'
import { DomainGrid } from './clinician/DomainGrid'
import { RiskHighlights } from './clinician/RiskHighlights'
import { SignOffDialog, type Decision } from './clinician/SignOffDialog'
import { TriageQueue, type QueueFilter } from './clinician/TriageQueue'
import { EmptyState, ErrorNotice, LoadingState, ProgressRing } from './ui'

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

      <main className="min-h-[60dvh] overflow-y-auto bg-canvas lg:min-h-0">
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
        ) : selectedId && !error ? (
          <LoadingState label="Loading check-in…" />
        ) : (
          <EmptyState icon={<Stethoscope aria-hidden className="size-6" />} title="Review prepared check-ins">
            <p>
              Each check-in in the queue holds a patient&apos;s own answers, organised by topic, with missing, contradictory and risk items
              already flagged.
            </p>
            <p className="mt-3">Choose one to read it, then approve it or request a follow-up. Nothing is final until you decide.</p>
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
  const [evidence, setEvidence] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [concerns, setConcerns] = useState(summary?.reported_concerns_summary ?? '')
  const [dialog, setDialog] = useState<Decision | null>(null)
  const [decision, setDecision] = useState<Decision>('approve')
  const [notes, setNotes] = useState('')

  if (!summary) {
    return (
      <EmptyState icon={<Inbox aria-hidden className="size-6" />} title="No summary yet">
        The patient has not finished or submitted this check-in, so there is nothing to review yet.
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

  const percent = Math.round(summary.completion_status.percentage)
  const userTurns = detail.messages.filter((m) => m.role === 'user').length

  return (
    <div className="mx-auto max-w-[1200px] px-5 py-7 sm:px-8 lg:py-9">
      {urgent && (
        <div role="alert" className="mb-6 flex items-start gap-3.5 rounded-2xl bg-rose-50 px-5 py-4 ring-1 ring-rose-200">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-rose-600 text-white">
            <AlertOctagon aria-hidden className="size-[18px]" />
          </span>
          <div className="text-sm text-rose-950">
            <p className="text-[15px] font-semibold">Safety concern disclosed</p>
            <p className="mt-0.5 text-rose-900">The check-in was paused and the patient was shown crisis support contacts. Review this case first.</p>
          </div>
        </div>
      )}

      {/* Header, decision panel and content share one grid, so the panel lines up with the case title. */}
      <div className="grid gap-x-10 gap-y-7 xl:grid-cols-[minmax(0,1fr)_300px]">
        <header className="order-1 min-w-0 xl:col-start-1 xl:row-start-1">
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-muted">Prepared by AI screening from the patient&apos;s own answers</p>
            <h1 className="mt-1 truncate font-display text-[2rem] leading-tight font-semibold tracking-tight text-ink">
              {detail.patient_alias ?? 'anonymous'}
            </h1>
            <p className="mt-1.5 text-sm text-muted">
              Started {formatDateTime(detail.created_at)}
              {early && ' · Sent before finishing'}
              {final?.summary_revised_by_clinician && ' · Summary edited by clinician'}
            </p>
          </div>
        </header>

        <div className="order-3 min-w-0 xl:col-start-1 xl:row-start-2">
          <Tabs
            value={tab}
            onChange={setTab}
            tabs={[
              { id: 'summary', label: 'Summary' },
              { id: 'conversation', label: 'Conversation', count: userTurns },
            ]}
          >
            {tab === 'summary' ? (
              <div className="space-y-11 pt-2">
                <Section
                  title="Overview"
                  actions={
                    pending &&
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
                        Edit summary
                      </button>
                    ))
                  }
                >
                  <div className="space-y-5">
                    <div className="space-y-2">
                      <p className="flex items-center gap-1.5 text-xs font-medium text-muted">
                        <UserRound aria-hidden className="size-3.5" />
                        Reported by the patient
                      </p>
                      <KeyMetrics data={detail.domain_data} />
                    </div>
                    {/* AI-drafted text is set apart from what the patient reported. */}
                    <div className="rounded-r-xl border-l-2 border-brand/40 bg-white/70 py-3 pr-4 pl-4">
                      <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-brand-strong">
                        <Sparkles aria-hidden className="size-3.5" />
                        {final?.summary_revised_by_clinician ? 'Summary, edited by a clinician' : 'AI-drafted summary · verify against the patient’s answers'}
                      </p>
                      {editing ? (
                        <textarea
                          aria-label="Edit the summary of reported concerns"
                          value={concerns}
                          onChange={(e) => setConcerns(e.target.value)}
                          rows={6}
                          className={cn(INPUT, 'py-3 leading-relaxed')}
                        />
                      ) : (
                        <Overview text={summary.reported_concerns_summary} />
                      )}
                    </div>
                    {pending && !pending.reflection_passed && (
                      <details className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200">
                        <summary className="cursor-pointer font-medium">The automatic quality check found issues. Read this summary carefully.</summary>
                        <p className="mt-1 whitespace-pre-wrap text-xs">{pending.reflection_feedback}</p>
                      </details>
                    )}
                  </div>
                </Section>

                <Section title="Areas for professional review" count={alerts.length}>
                  <RiskHighlights
                    alerts={alerts}
                    onShowEvidence={(quote) => {
                      setEvidence(quote)
                      setTab('conversation')
                    }}
                  />
                </Section>

                {detail.inconsistencies.length > 0 && (
                  <Section title="Answers to double-check" count={detail.inconsistencies.length} hint="Some answers point in different directions">
                    <Inconsistencies items={detail.inconsistencies} />
                  </Section>
                )}

                <Section title="Answers by topic" hint="As reported by the patient">
                  <DomainGrid data={detail.domain_data} progress={detail.domain_completion_map} />
                </Section>

                <Section title="Missing information" count={detail.missing_fields.length}>
                  <MissingFields fields={detail.missing_fields} />
                </Section>

                {/* Non-diagnostic notice */}
                <footer title={summary.non_diagnostic_disclaimer} className="flex items-start gap-2.5 border-t border-line pt-5 text-[13px] text-muted">
                  <Info aria-hidden className="mt-0.5 size-4 shrink-0" />
                  <p>
                    <span className="font-semibold text-ink">Screening summary only.</span> Not a medical diagnosis. Decisions about care rest with
                    the reviewing clinician.
                  </p>
                </footer>
              </div>
            ) : (
              <Transcript detail={detail} evidence={evidence} />
            )}
          </Tabs>
        </div>

        {/* Decision panel: the case at a glance and the clinician's actions, always in reach. */}
        <aside aria-label="Review decision" className="order-2 xl:col-start-2 xl:row-span-2 xl:row-start-1">
          <div className="space-y-5 rounded-2xl bg-white p-5 shadow-card ring-1 ring-line/70 xl:sticky xl:top-6">
            <div className="flex items-center gap-4">
              <ProgressRing value={percent} label="Questions answered" size="3.25rem" />
              <div className="min-w-0 space-y-1">
                <p className={cn('flex items-center gap-1.5 text-[15px] font-semibold', PRIORITY_TEXT[priority])} title={`Highest risk flag: ${RISK_LABELS[riskLevel]}`}>
                  <span aria-hidden className={cn('size-2 rounded-full', PRIORITY_DOT[priority])} />
                  {PRIORITY_LABEL[priority]}
                </p>
                <p className="text-[13px] text-muted">{STAGE_TEXT[displayStage(detail.status, urgent)]}</p>
              </div>
            </div>

            <QualityCheck passed={pending?.reflection_passed ?? detail.reflection_passed} attempts={detail.reflection_attempts} />

            {pending ? (
              <div className="space-y-2.5 border-t border-line pt-5">
                <p className="text-sm font-semibold text-ink">Your decision</p>
                <p className="text-[13px] leading-relaxed text-muted">Read the summary and the patient&apos;s answers, then choose one.</p>
                <button type="button" onClick={() => openSignOff('approve')} className={cn(buttonClass('primary'), 'w-full')}>
                  <CheckCircle2 aria-hidden className="size-4" />
                  Approve &amp; sign off
                </button>
                <button type="button" onClick={() => openSignOff('follow_up')} className={cn(buttonClass('danger'), 'w-full')}>
                  <Flag aria-hidden className="size-4" />
                  Request follow-up
                </button>
              </div>
            ) : (
              final && (
                <div className="space-y-3 border-t border-line pt-5">
                  <p className={cn('flex items-center gap-2 text-sm font-semibold', final.clinician_approved ? 'text-emerald-700' : 'text-amber-800')}>
                    {final.clinician_approved ? <CheckCircle2 aria-hidden className="size-4" /> : <Flag aria-hidden className="size-4" />}
                    {final.clinician_approved ? 'Signed off' : 'Follow-up requested'}
                  </p>
                  <p className="text-[13px] text-muted">{formatDateTime(final.reviewed_at)}</p>
                  {final.clinician_notes && (
                    <div className="rounded-xl bg-slate-50 px-3.5 py-3">
                      <p className={EYEBROW}>Clinician notes</p>
                      <p className="mt-1 text-sm whitespace-pre-wrap text-ink">{final.clinician_notes}</p>
                    </div>
                  )}
                </div>
              )
            )}
            <Timeline detail={detail} />
          </div>
        </aside>
      </div>

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

const STAGE_TEXT: Record<DisplayStage, string> = {
  in_progress: 'Patient still answering',
  paused: 'Patient paused the check-in',
  priority_review: 'Interrupted for safety · review first',
  submitted: 'Submitted · waiting for your review',
  reviewed: 'Review complete',
}

const PRIORITY_LABEL: Record<TriagePriority, string> = { urgent: 'Urgent', high: 'High priority', routine: 'Routine' }
const PRIORITY_TEXT: Record<TriagePriority, string> = { urgent: 'text-rose-700', high: 'text-amber-800', routine: 'text-ink' }
const PRIORITY_DOT: Record<TriagePriority, string> = { urgent: 'bg-rose-500', high: 'bg-amber-500', routine: 'bg-slate-300' }

/**
 * Result of the automatic summary check (graph reflect_summary node): no diagnostic wording,
 * every missing, conflicting and risk item covered. Shown in plain words; details sit in the Overview.
 */
function QualityCheck({ passed, attempts }: { passed: boolean | null; attempts: number }) {
  if (passed === null) return null
  // Urgent cases skip the check: their summary is assembled by fixed rules, with no AI-written text.
  if (attempts === 0) {
    return passed ? (
      <p className="flex items-start gap-2 text-[13px] leading-snug text-muted">
        <ShieldCheck aria-hidden className="mt-px size-4 shrink-0 text-muted" />
        Urgent summary built from fixed safety rules
      </p>
    ) : null
  }
  return (
    <p
      className={cn('flex items-start gap-2 text-[13px] leading-snug', passed ? 'text-muted' : 'text-amber-800')}
      title="Checked for diagnostic wording and that every missing, conflicting and risk item is included"
    >
      {passed ? (
        <ShieldCheck aria-hidden className="mt-px size-4 shrink-0 text-emerald-600" />
      ) : (
        <AlertTriangle aria-hidden className="mt-px size-4 shrink-0 text-amber-600" />
      )}
      <span>
        {passed ? 'Summary passed the automatic quality check' : 'Summary did not pass the automatic quality check'}
        {attempts > 1 && <span className="text-muted"> · rewritten {attempts - 1} time{attempts > 2 ? 's' : ''}</span>}
      </span>
    </p>
  )
}

interface SectionProps {
  title: string
  count?: number
  hint?: string
  actions?: ReactNode
  children: ReactNode
}

/** A titled region of the review page: a heading row, then content. No card of its own. */
function Section({ title, count, hint, actions, children }: SectionProps) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId}>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={headingId} className="font-display text-xl font-semibold tracking-tight text-ink">
          {title}
          {count !== undefined && count > 0 && <span className="ml-2 font-sans text-sm font-medium text-muted tabular-nums">{count}</span>}
        </h2>
        {hint && <p className="text-sm text-muted">{hint}</p>}
        {actions && <div className="-my-1 flex items-center gap-1">{actions}</div>}
      </div>
      {children}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Key metrics & overview
// ---------------------------------------------------------------------------

type MetricTone = 'ok' | 'warn' | 'danger' | 'none'

const METRIC_TONES: Record<MetricTone, { dot: string; text: string }> = {
  ok: { dot: 'bg-emerald-500', text: 'text-ink' },
  warn: { dot: 'bg-amber-500', text: 'text-amber-900' },
  danger: { dot: 'bg-rose-500', text: 'text-rose-800' },
  none: { dot: 'bg-slate-200', text: 'text-slate-400' },
}

const SEVERITY_TONES: Record<string, MetricTone> = {
  none: 'ok', occasional: 'warn', mild: 'warn', frequent: 'danger', moderate: 'danger', severe: 'danger',
}  // fmt: skip

/** Mood · Stress · Sleep · Panic · Functioning at a glance; the domain grid below has the detail. */
function KeyMetrics({ data }: { data: AssessmentDomainData }) {
  const mood = data.mood?.overall_mood_rating
  const stress = data.stress?.perceived_stress_level
  const sleep = data.sleep?.average_sleep_hours
  const panic = data.anxiety?.panic_attacks
  const impact = data.functioning?.work_study_impact
  const metrics: { label: string; value: string | null; tone: MetricTone; hint: string }[] = [
    { label: 'Mood', value: mood == null ? null : `${mood}/10`, tone: mood == null ? 'none' : mood <= 3 ? 'danger' : mood <= 5 ? 'warn' : 'ok', hint: 'Self-rated mood' },
    { label: 'Stress', value: stress == null ? null : `${stress}/10`, tone: stress == null ? 'none' : stress >= 8 ? 'danger' : stress >= 5 ? 'warn' : 'ok', hint: 'Perceived stress' },
    { label: 'Sleep', value: sleep == null ? null : `${sleep}h`, tone: sleep == null ? 'none' : sleep < 4 ? 'danger' : sleep < 6 ? 'warn' : 'ok', hint: 'Average sleep per night' },
    { label: 'Panic', value: panic ? humanize(panic) : null, tone: panic ? (SEVERITY_TONES[panic] ?? 'none') : 'none', hint: 'Panic attacks' },
    { label: 'Functioning', value: impact ? humanize(impact) : null, tone: impact ? (SEVERITY_TONES[impact] ?? 'none') : 'none', hint: 'Impact on work/study' },
  ]
  return (
    <dl className="grid grid-cols-2 overflow-hidden rounded-2xl bg-white shadow-card ring-1 ring-line/70 sm:grid-cols-5 sm:divide-x sm:divide-line/70">
      {metrics.map((m) => (
        <div key={m.label} title={m.hint} className="px-4 py-3.5">
          <dt className="flex items-center gap-1.5 text-xs font-medium text-muted">
            <span aria-hidden className={cn('size-1.5 rounded-full', METRIC_TONES[m.tone].dot)} />
            {m.label}
          </dt>
          <dd className={cn('mt-1 text-lg font-semibold tabular-nums', METRIC_TONES[m.tone].text)}>
            {m.value ?? (
              <span title="Not given" aria-label="Not given">
                —
              </span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}

/** The first two sentences, with the full summary one click away. */
function Overview({ text }: { text: string }) {
  const sentences = text.match(/[^.!?]+[.!?]+(?=\s|$)|[^.!?]+$/g)?.map((t) => t.trim()) ?? [text]
  const lead = sentences.slice(0, 2).join(' ')
  if (sentences.length <= 2) return <p className="text-sm leading-relaxed text-slate-700">{text}</p>
  return (
    <details className="group text-sm leading-relaxed text-slate-700">
      <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
        <span className="group-open:hidden">
          {lead} <span className="whitespace-nowrap text-xs font-medium text-accent">More</span>
        </span>
        <span className="hidden text-xs font-medium text-accent group-open:inline">Less</span>
      </summary>
      <p className="mt-1">{text}</p>
    </details>
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
      <div role="tablist" aria-label="Check-in views" onKeyDown={onKeyDown} className="flex gap-6 border-b border-line">
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
                selected ? 'text-ink after:absolute after:inset-x-0 after:bottom-0 after:border-b-2 after:border-accent' : 'text-muted hover:text-ink',
              )}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className="rounded-full bg-slate-100 px-1.5 text-xs tabular-nums text-slate-600">{tab.count}</span>
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

function Transcript({ detail, evidence }: { detail: AssessmentDetail; evidence: string | null }) {
  const messages = detail.messages.filter((m) => (m.role === 'user' || m.role === 'assistant') && m.content.trim())
  // Quotes are windows around the matched words; matching on their core finds the source message.
  const needle = evidence?.replace(/^[\s.…"“]+|[\s.…"”]+$/g, '').slice(0, 40).toLowerCase() ?? null
  const isSource = (m: (typeof messages)[number]) => m.role === 'user' && !!needle && m.content.toLowerCase().includes(needle)
  const firstSource = useRef<HTMLLIElement>(null)
  const firstIndex = messages.findIndex(isSource)

  useEffect(() => {
    firstSource.current?.scrollIntoView({ block: 'center' })
  }, [firstIndex])

  return (
    <div className="space-y-3">
      {needle && (
        <p className="text-sm text-muted">
          {firstIndex >= 0 ? 'Highlighted: the patient message behind the selected review area.' : 'The quoted words were not found in this conversation.'}
        </p>
      )}
      <ol className={cn(CARD, 'divide-y divide-line')}>
        {messages.map((m, i) => (
          <li
            key={m.id ?? i}
            ref={i === firstIndex ? firstSource : undefined}
            className={cn('flex gap-3 px-5 py-3.5', isSource(m) && 'bg-amber-50/80 ring-1 ring-inset ring-amber-200')}
          >
            <span
              aria-hidden
              className={cn(
                'grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold',
                m.role === 'user' ? 'bg-teal-50 text-accent' : 'bg-teal-50 text-brand',
              )}
            >
              {m.role === 'user' ? 'Pt' : <Sparkles className="size-3.5" />}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                {m.role === 'user' ? 'Patient' : 'Assistant'}
                {m.created_at && <span className="ml-2 font-normal normal-case tracking-normal">{formatTime(m.created_at)}</span>}
                {isSource(m) && <span className="ml-2 normal-case tracking-normal text-amber-800">Source</span>}
              </p>
              <p className="whitespace-pre-wrap text-sm text-ink">{m.content}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Timeline (from message timestamps and the review record; nothing is estimated)
// ---------------------------------------------------------------------------

interface TimelineEvent {
  at: string
  label: string
  tone?: 'danger' | 'ok'
  /** Topics whose answers were first saved at this point (consecutive saves are shown as one row). */
  topics?: string[]
  until?: string
}

function timelineEvents(detail: AssessmentDetail): TimelineEvent[] {
  const events: TimelineEvent[] = []
  if (detail.created_at) events.push({ at: detail.created_at, label: 'Check-in started' })
  const saved = new Set<string>()
  for (const m of detail.messages) {
    if (!m.created_at) continue
    if (m.role === 'tool' && m.name === 'store_assessment_response') {
      try {
        const result = JSON.parse(m.content) as { ok?: boolean; domain?: AssessmentDomain }
        if (result.ok && result.domain && !saved.has(result.domain)) {
          saved.add(result.domain)
          const topic = DOMAIN_META[result.domain].short
          const last = events.at(-1)
          if (last?.topics) {
            last.topics.push(topic)
            last.until = m.created_at
          } else {
            events.push({ at: m.created_at, label: '', topics: [topic] })
          }
        }
      } catch {
        // not a store result
      }
    } else if (m.role === 'assistant') {
      // The backend's fixed (non-model) messages mark these moments.
      if (m.content.includes("I'm pausing the screening so a mental health professional")) {
        events.push({ at: m.created_at, label: 'Safety concern disclosed · check-in paused', tone: 'danger' })
      } else if (m.content.startsWith('Your progress is saved')) {
        events.push({ at: m.created_at, label: 'Paused by the patient' })
      } else if (/^Thank(s| you), your answers are now with a clinician/.test(m.content)) {
        events.push({ at: m.created_at, label: detail.pending_review?.early_submission || detail.final_output?.early_submission ? 'Sent before finishing' : 'Sent for review' })
      }
    }
  }
  if (detail.final_output?.reviewed_at) {
    events.push({
      at: detail.final_output.reviewed_at,
      label: detail.final_output.clinician_approved ? 'Signed off by clinician' : 'Follow-up requested by clinician',
      tone: 'ok',
    })
  }
  for (const e of events) {
    if (e.topics) e.label = `Answers saved: ${e.topics.join(', ')}`
  }
  return events.sort((a, b) => a.at.localeCompare(b.at))
}

function Timeline({ detail }: { detail: AssessmentDetail }) {
  const events = timelineEvents(detail)
  if (events.length === 0) return null
  return (
    <div className="space-y-3 border-t border-line pt-5">
      <p className="text-sm font-semibold text-ink">Timeline</p>
      <ol className="relative space-y-3 before:absolute before:top-1.5 before:bottom-1.5 before:left-[3px] before:w-px before:bg-line">
        {events.map((e, i) => (
          <li key={`${e.at}-${i}`} className="relative flex gap-3 pl-4 text-[13px]">
            <span
              aria-hidden
              className={cn(
                'absolute top-1.5 left-0 size-[7px] rounded-full',
                e.tone === 'danger' ? 'bg-rose-500' : e.tone === 'ok' ? 'bg-emerald-500' : 'bg-slate-300',
              )}
            />
            <span className="min-w-0 flex-1 text-ink">{e.label}</span>
            <time
              dateTime={e.at}
              className="shrink-0 tabular-nums text-muted"
              title={e.until ? `${formatDateTime(e.at)} – ${formatDateTime(e.until)}` : formatDateTime(e.at)}
            >
              {formatTime(e.at)}
            </time>
          </li>
        ))}
      </ol>
    </div>
  )
}
