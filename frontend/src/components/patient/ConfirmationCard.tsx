import { CalendarCheck, CheckCircle2, HeartHandshake, Phone, ShieldCheck } from 'lucide-react'
import { formatDateTime } from '../../lib/format'
import { CARD, cn } from '../../lib/styles'
import { ASSESSMENT_DOMAINS, type AssessmentDetail } from '../../types/api'

/**
 * Reassuring end-of-intake card for the patient. Deliberately shows no audit tags, risk codes
 * or clinician notes: those belong to the clinician workspace.
 */
export function ConfirmationCard({ detail }: { detail: AssessmentDetail }) {
  const reviewed = detail.status === 'reviewed'
  const completedAreas = ASSESSMENT_DOMAINS.filter((d) => detail.domain_completion_map[d]?.completed).length
  const submittedAt =
    detail.final_output?.reviewed_at && reviewed
      ? detail.final_output.reviewed_at
      : ([...detail.messages].reverse().find((m) => m.created_at)?.created_at ?? detail.updated_at)

  return (
    <article aria-labelledby="confirmation-title" className={cn(CARD, 'overflow-hidden')}>
      <div className="bg-gradient-to-br from-teal-50 via-white to-indigo-50/40 px-6 py-6">
        <div className="flex items-start gap-4">
          <div className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white text-brand shadow-card ring-1 ring-line">
            {reviewed ? <ShieldCheck aria-hidden className="size-6" /> : <CheckCircle2 aria-hidden className="size-6" />}
          </div>
          <div className="space-y-1">
            <h2 id="confirmation-title" className="text-lg font-semibold tracking-tight text-ink">
              {reviewed ? 'Your intake has been reviewed' : 'Thank you. Your answers have been submitted'}
            </h2>
            <p className="text-sm text-slate-600">
              {reviewed
                ? 'A qualified clinician has read your screening and will follow up with you about next steps.'
                : 'A qualified clinician is now reviewing your intake. You don’t need to do anything else right now.'}
            </p>
          </div>
        </div>
      </div>

      <dl className="grid grid-cols-1 divide-y divide-line border-t border-line sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <div className="flex items-center gap-3 px-6 py-4">
          <CalendarCheck aria-hidden className="size-5 text-slate-400" />
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{reviewed ? 'Reviewed' : 'Submitted'}</dt>
            <dd className="text-sm font-medium text-ink">{formatDateTime(submittedAt)}</dd>
          </div>
        </div>
        <div className="flex items-center gap-3 px-6 py-4">
          <CheckCircle2 aria-hidden className="size-5 text-slate-400" />
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Completed</dt>
            <dd className="text-sm font-medium text-ink">
              {completedAreas} of 6 areas · {Math.round(detail.completion_pct)}%
            </dd>
          </div>
        </div>
        <div className="flex items-center gap-3 px-6 py-4">
          <HeartHandshake aria-hidden className="size-5 text-slate-400" />
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Status</dt>
            <dd className="text-sm font-medium text-ink">{reviewed ? 'Reviewed by a clinician' : 'With a clinician'}</dd>
          </div>
        </div>
      </dl>

      <div className="flex items-start gap-2 border-t border-line bg-slate-50 px-6 py-3 text-xs text-slate-600">
        <Phone aria-hidden className="mt-0.5 size-3.5 shrink-0" />
        <p>
          This screening is not a diagnosis. If you feel unsafe at any point, call your local emergency number, or call or
          text <strong>988</strong> (US) · Samaritans <strong>116 123</strong> (UK &amp; Ireland) ·{' '}
          <a className="underline" href="https://findahelpline.com" target="_blank" rel="noreferrer">
            findahelpline.com
          </a>
          .
        </p>
      </div>
    </article>
  )
}
