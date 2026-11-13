import { Check, ClipboardCheck, History, PauseCircle, Plus } from 'lucide-react'
import { DOMAIN_META } from '../../lib/domains'
import { summarizeCheckIn } from '../../lib/outcome'
import { buttonClass, cn, EYEBROW } from '../../lib/styles'
import { ASSESSMENT_DOMAINS, type AssessmentDetail } from '../../types/api'

interface ProgressRailProps {
  detail: AssessmentDetail
  locked: boolean
  busy: boolean
  creating: boolean
  onPause: () => void
  onSubmit: () => void
  onOpenSessions: () => void
  onNewSession: () => void
}

const NEXT_TEXT = {
  safety_pause: 'Your check-in is paused for your safety. A clinician will review what you shared first; the support contacts at the top of the page are there if you need them now.',
  sent_partial: 'Your answers so far are with a clinician. Topics you did not reach are listed for them as not answered.',
  sent_complete: 'Your answers are with a clinician. Nothing else is needed from you right now.',
  reviewed: 'A clinician has reviewed your check-in and will follow up with you.',
} as const

/** Desktop side rail: where you are, what is left, what happens next, and the session actions. */
export function ProgressRail({ detail, locked, busy, creating, onPause, onSubmit, onOpenSessions, onNewSession }: ProgressRailProps) {
  const progress = detail.domain_completion_map
  const percent = Math.round(detail.completion_pct)
  const current = ASSESSMENT_DOMAINS.find((domain) => !progress[domain]?.completed)
  const { questionsAnswered, questionsTotal } = summarizeCheckIn(detail)
  const paused = detail.status === 'interrupted'

  return (
    <aside aria-label="Check-in progress" className="hidden w-[300px] shrink-0 flex-col border-r border-line/80 lg:flex">
      <div className="flex-1 space-y-6 overflow-y-auto px-6 pt-7 pb-5 [scrollbar-width:thin]">
        <div className="space-y-1">
          <p className={EYEBROW}>Your check-in</p>
          <p className="truncate font-display text-xl font-semibold text-ink">{detail.patient_alias ?? 'Anonymous'}</p>
        </div>

        <div className="space-y-2.5">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-muted">{locked ? 'Answered' : paused ? 'Paused at' : 'Progress'}</span>
            <span className="font-display text-3xl font-semibold tabular-nums text-ink">{percent}%</span>
          </div>
          <progress className={cn('meter', percent >= 100 && 'complete')} max={100} value={percent} aria-label="Check-in progress" />
          <p className="text-xs text-muted">
            {questionsAnswered} of {questionsTotal} questions answered
          </p>
        </div>

        <ol className="relative space-y-0.5">
          {ASSESSMENT_DOMAINS.map((domain, index) => {
            const meta = DOMAIN_META[domain]
            const Icon = meta.icon
            const state = progress[domain]?.completed ? 'done' : domain === current && !locked ? 'current' : 'todo'
            return (
              <li
                key={domain}
                aria-current={state === 'current' ? 'step' : undefined}
                className={cn('flex items-center gap-3 rounded-xl px-2.5 py-1.5', state === 'current' && 'bg-white shadow-card')}
              >
                <span
                  className={cn(
                    'grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold',
                    state === 'done' && 'bg-brand text-white',
                    state === 'current' && 'bg-brand-soft text-brand-strong ring-1 ring-brand/30',
                    state === 'todo' && 'bg-slate-100 text-slate-400',
                  )}
                >
                  {state === 'done' ? <Check aria-hidden className="size-3.5" strokeWidth={3} /> : <Icon aria-hidden className="size-3.5" />}
                </span>
                <span className={cn('flex-1 text-sm', state === 'todo' ? 'text-muted' : 'font-medium text-ink')}>
                  <span className="sr-only">{index + 1}. </span>
                  {meta.title}
                </span>
                <span className="text-xs text-muted tabular-nums">
                  {state === 'done' ? 'Done' : state === 'current' ? 'Now' : progress[domain]?.answered ? 'Started' : ''}
                </span>
              </li>
            )
          })}
        </ol>

        <div className="space-y-1.5 border-t border-line pt-5">
          <p className="text-sm font-semibold text-ink">What happens next</p>
          <p className="text-sm leading-relaxed text-muted">
            {!locked
              ? 'When all six topics are covered, your answers go to a clinician. You can also send them sooner.'
              : NEXT_TEXT[summarizeCheckIn(detail).outcome]}
          </p>
        </div>
      </div>

      <div className="space-y-2 border-t border-line/80 px-6 py-4">
        {!locked && (
          <>
            {detail.status !== 'interrupted' && (
              <button type="button" disabled={busy} onClick={onPause} className={cn(buttonClass('secondary'), 'w-full')}>
                <PauseCircle aria-hidden className="size-4" />
                Pause and save
              </button>
            )}
            <button type="button" disabled={busy} onClick={onSubmit} className={cn(buttonClass('ghost'), 'w-full text-brand-strong')}>
              <ClipboardCheck aria-hidden className="size-4" />
              Send answers to clinician
            </button>
          </>
        )}
        <div className="flex justify-between pt-1">
          <button type="button" onClick={onOpenSessions} aria-haspopup="dialog" className={buttonClass('ghost', 'sm')}>
            <History aria-hidden className="size-3.5" />
            Saved check-ins
          </button>
          <button type="button" onClick={onNewSession} disabled={creating} className={buttonClass('ghost', 'sm')}>
            <Plus aria-hidden className="size-3.5" />
            New Session
          </button>
        </div>
      </div>
    </aside>
  )
}
