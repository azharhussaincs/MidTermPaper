import { ASSESSMENT_DOMAINS, type AssessmentDetail } from '../types/api'

/**
 * How a locked check-in ended, in the patient's terms. One source for the confirmation card, the
 * progress rail and the composer footer, so they never contradict each other (e.g. "Submitted,
 * nothing else to do" next to crisis instructions, or "Completed" on a 22% check-in).
 */
export type CheckInOutcome =
  | 'safety_pause' // a safety-critical disclosure stopped the check-in; a clinician reviews it first
  | 'sent_partial' // sent to a clinician before every topic was covered
  | 'sent_complete' // every topic covered and sent
  | 'reviewed' // a clinician has signed it off

export interface CheckInSummary {
  outcome: CheckInOutcome
  /** True whenever a safety concern was raised, including after review. */
  safetyConcern: boolean
  topicsCovered: number
  /** Required questions answered / in total, summed from the backend's per-topic counts. */
  questionsAnswered: number
  questionsTotal: number
  /** The backend's completion_pct (answered / total required, the same audit), rounded. */
  percent: number
}

export function summarizeCheckIn(detail: AssessmentDetail): CheckInSummary {
  const progress = ASSESSMENT_DOMAINS.map((d) => detail.domain_completion_map[d])
  const topicsCovered = progress.filter((p) => p?.completed).length
  const questionsAnswered = progress.reduce((sum, p) => sum + (p?.answered ?? 0), 0)
  const questionsTotal = progress.reduce((sum, p) => sum + (p?.required ?? 0), 0)
  const safetyConcern = detail.requires_urgent_escalation
  const outcome: CheckInOutcome =
    detail.status === 'reviewed'
      ? 'reviewed'
      : safetyConcern
        ? 'safety_pause'
        : topicsCovered < ASSESSMENT_DOMAINS.length
          ? 'sent_partial'
          : 'sent_complete'
  return { outcome, safetyConcern, topicsCovered, questionsAnswered, questionsTotal, percent: Math.round(detail.completion_pct) }
}
