import { CalendarCheck, CheckCircle2, HeartHandshake, Info, LifeBuoy, ListChecks, Phone, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { formatDateTime } from '../../lib/format'
import { summarizeCheckIn, type CheckInOutcome } from '../../lib/outcome'
import { CARD, cn } from '../../lib/styles'
import { ASSESSMENT_DOMAINS, type AssessmentDetail } from '../../types/api'

const COPY: Record<CheckInOutcome, { title: string; body: (answered: number, total: number) => string; next: string }> = {
  safety_pause: {
    title: 'Your check-in is paused for your safety',
    body: () =>
      'A clinician has been alerted and will look at what you shared first. If you might act on these thoughts or are not safe, use the support contacts at the top of this page now.',
    next: 'Priority clinician review',
  },
  sent_partial: {
    title: 'Sent to a clinician',
    body: (answered, total) =>
      `You answered ${answered} of ${total} questions before sending. A clinician will review what you shared; nothing you answered is lost.`,
    next: 'Clinician review',
  },
  sent_complete: {
    title: 'Sent to a clinician. Thank you',
    body: () => 'You covered all six topics. A clinician will review your answers before your appointment.',
    next: 'Clinician review',
  },
  reviewed: {
    title: 'Reviewed by a clinician',
    body: () => 'They will follow up with you about next steps.',
    next: 'Review complete',
  },
}

/**
 * End-of-check-in card for the patient. It states what actually happened (paused for safety,
 * sent early, sent complete, reviewed) and deliberately shows no audit tags, risk codes or
 * clinician notes: those belong to the clinician workspace.
 */
export function ConfirmationCard({ detail }: { detail: AssessmentDetail }) {
  const { outcome, safetyConcern, topicsCovered, questionsAnswered, questionsTotal, percent } = summarizeCheckIn(detail)
  const copy = COPY[outcome]
  const safety = outcome === 'safety_pause'
  const lastActivity =
    outcome === 'reviewed' && detail.final_output?.reviewed_at
      ? detail.final_output.reviewed_at
      : ([...detail.messages].reverse().find((m) => m.created_at)?.created_at ?? detail.updated_at)

  return (
    <article aria-labelledby="confirmation-title" className={cn(CARD, 'overflow-hidden')}>
      <div className={cn('px-6 py-6', safety ? 'bg-rose-50' : 'bg-brand-soft/60')}>
        <div className="flex items-start gap-4">
          <div
            className={cn(
              'grid size-12 shrink-0 place-items-center rounded-2xl bg-white shadow-card ring-1',
              safety ? 'text-rose-600 ring-rose-200' : 'text-brand ring-line',
            )}
          >
            {safety ? (
              <LifeBuoy aria-hidden className="size-6" />
            ) : outcome === 'reviewed' ? (
              <ShieldCheck aria-hidden className="size-6" />
            ) : (
              <CheckCircle2 aria-hidden className="size-6" />
            )}
          </div>
          <div className="space-y-1">
            <h2 id="confirmation-title" className={cn('text-lg font-semibold tracking-tight', safety ? 'text-rose-950' : 'text-ink')}>
              {copy.title}
            </h2>
            <p className={cn('text-sm leading-relaxed', safety ? 'text-rose-900' : 'text-slate-600')}>{copy.body(questionsAnswered, questionsTotal)}</p>
          </div>
        </div>
      </div>

      <dl className="grid grid-cols-1 divide-y divide-line border-t border-line sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <Fact icon={<CalendarCheck aria-hidden className="size-5" />} term={outcome === 'reviewed' ? 'Reviewed' : safety ? 'Paused' : 'Sent'}>
          {formatDateTime(lastActivity)}
        </Fact>
        <Fact icon={<ListChecks aria-hidden className="size-5" />} term="Answered">
          <span className="block">
            {questionsAnswered} of {questionsTotal} questions ({percent}%)
          </span>
          <span className="block text-xs font-normal text-muted">
            {topicsCovered} of {ASSESSMENT_DOMAINS.length} topics complete
          </span>
        </Fact>
        <Fact icon={<HeartHandshake aria-hidden className="size-5" />} term="Next step">
          {copy.next}
        </Fact>
      </dl>

      <div className="flex items-start gap-2 border-t border-line bg-slate-50 px-6 py-3 text-xs text-slate-600">
        {safety ? <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" /> : <Phone aria-hidden className="mt-0.5 size-3.5 shrink-0" />}
        {/* After a safety pause the crisis contacts are already pinned at the top of the page. */}
        <p>
          {safety ? null : (
            <>
              {safetyConcern ? 'If you feel unsafe at any time' : 'Feel unsafe?'}, call your local emergency number or find a free crisis line in
              your country at{' '}
              <a className="underline" href="https://findahelpline.com" target="_blank" rel="noreferrer">
                findahelpline.com
              </a>
              .{' '}
            </>
          )}
          This check-in is not a diagnosis.
        </p>
      </div>
    </article>
  )
}

function Fact({ icon, term, children }: { icon: ReactNode; term: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3 px-6 py-4">
      <span className="text-slate-400">{icon}</span>
      <div>
        <dt className="text-xs font-semibold uppercase tracking-wider text-muted">{term}</dt>
        <dd className="text-sm font-medium text-ink">{children}</dd>
      </div>
    </div>
  )
}
