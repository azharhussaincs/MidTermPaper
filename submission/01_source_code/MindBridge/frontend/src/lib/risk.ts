import type { AssessmentSummaryOutput, QueueItem, RiskFlag, RiskLevel } from '../types/api'
import { humanize, splitTag } from './format'

const LEVEL_RANK: Record<RiskLevel, number> = { critical: 0, high: 1, elevated: 2, none: 3 }

const CODE_LABELS: Record<string, string> = {
  self_harm_language: 'Self-harm language',
  harm_to_others_language: 'Harm-to-others language',
  hopelessness_language: 'Hopelessness language',
  panic_language: 'Panic language',
  self_harm_thoughts: 'Reports thoughts of self-harm',
  severe_hopelessness: 'Severe hopelessness',
  moderate_hopelessness: 'Moderate hopelessness',
  phq2_positive_screen: 'PHQ-2 positive screen',
  gad2_positive_screen: 'GAD-2 positive screen',
  low_wellbeing_index: 'Low WHO-5 wellbeing index',
  severe_panic: 'Severe panic attacks',
  frequent_panic: 'Frequent panic attacks',
  extreme_stress: 'Extreme stress',
  severe_sleep_deprivation: 'Severe sleep deprivation',
  hypersomnia_indicator: 'Hypersomnia indicator',
  extreme_functional_impairment: 'Extreme functional impairment',
  functional_impairment: 'Functional impairment',
}

export function riskLabel(code: string): string {
  return CODE_LABELS[code] ?? humanize(code)
}

export interface RiskAlert {
  level: RiskLevel
  urgent: boolean
  /** One risk type per alert, e.g. "Panic language". */
  label: string
  /** Distinct triggers for this risk type: the patient's words or the structured evidence. */
  evidence: string[]
  quoted: boolean
  action: string | null
}

/** Strips "User said:" / "Wrote:" and the "…" padding so identical triggers compare equal. */
function normaliseEvidence(evidence: string): { text: string; quoted: boolean } {
  const match = /^(User said|Wrote):\s*(.*)$/s.exec(evidence.trim())
  if (!match) return { text: evidence.trim().replaceAll('_', ' ').replaceAll('=', ': '), quoted: false }
  return { text: match[2].replace(/^\.\.\.|\.\.\.$/g, '').trim(), quoted: true }
}

/**
 * Quotes of the same sentence arrive as different windows around each match
 * ("…n't. Everything feels hopeless…" vs "I don't. Everything feels hopeless…"), so two quotes
 * are the same trigger when one contains the other or they share a 30+ character run.
 */
function sameTrigger(a: string, b: string): boolean {
  const [shorter, longer] = a.length <= b.length ? [a, b] : [b, a]
  if (longer.includes(shorter)) return true
  const run = Math.min(30, shorter.length)
  for (let i = 0; i + run <= shorter.length; i++) {
    if (longer.includes(shorter.slice(i, i + run))) return true
  }
  return false
}

function addEvidence(alert: RiskAlert, text: string): void {
  const index = alert.evidence.findIndex((known) => sameTrigger(known, text))
  if (index < 0) alert.evidence.push(text)
  else if (text.length > alert.evidence[index].length) alert.evidence[index] = text // keep the fullest quote
}

function sortAlerts(alerts: RiskAlert[]): RiskAlert[] {
  return alerts.sort((a, b) => Number(b.urgent) - Number(a.urgent) || LEVEL_RANK[a.level] - LEVEL_RANK[b.level])
}

/** One alert per risk type: repeated flags of the same code (e.g. several panic phrases) merge into one. */
export function groupRiskFlags(flags: RiskFlag[]): RiskAlert[] {
  const byCode = new Map<string, RiskAlert>()
  for (const flag of flags) {
    const { text, quoted } = normaliseEvidence(flag.evidence)
    const existing = byCode.get(flag.code)
    if (existing) {
      addEvidence(existing, text)
      existing.urgent ||= flag.requires_immediate_escalation
      if (LEVEL_RANK[flag.level] < LEVEL_RANK[existing.level]) existing.level = flag.level
      if (flag.requires_immediate_escalation) existing.action = flag.recommended_action
      continue
    }
    byCode.set(flag.code, {
      level: flag.level,
      urgent: flag.requires_immediate_escalation,
      label: riskLabel(flag.code),
      evidence: [text],
      quoted,
      action: flag.requires_immediate_escalation ? flag.recommended_action : null,
    })
  }
  return sortAlerts([...byCode.values()])
}

/** Fallback when only the summary text is available: "[R#] URGENT: HIGH - code: evidence" entries, one per code. */
export function groupSummaryReviewAreas(summary: AssessmentSummaryOutput): RiskAlert[] {
  const byCode = new Map<string, RiskAlert>()
  for (const entry of summary.areas_requiring_professional_review) {
    const { text } = splitTag(entry)
    const urgent = /URGENT/i.test(text)
    const body = text.replace(/^URGENT:\s*/i, '')
    const match = /^(CRITICAL|HIGH|ELEVATED)\s*-\s*([a-z_0-9]+):\s*(.*)$/is.exec(body)
    const level = (match?.[1].toLowerCase() as RiskLevel | undefined) ?? (urgent ? 'critical' : 'elevated')
    const code = match?.[2] ?? body
    const { text: evidence, quoted } = normaliseEvidence(match?.[3] ?? body)
    const existing = byCode.get(code)
    if (existing) {
      addEvidence(existing, evidence)
      existing.urgent ||= urgent
      if (LEVEL_RANK[level] < LEVEL_RANK[existing.level]) existing.level = level
      continue
    }
    byCode.set(code, { level, urgent, label: match ? riskLabel(code) : 'Flagged for review', evidence: [evidence], quoted, action: null })
  }
  return sortAlerts([...byCode.values()])
}

export function highestLevel(levels: RiskLevel[]): RiskLevel {
  return (['critical', 'high', 'elevated'] as const).find((level) => levels.includes(level)) ?? 'none'
}

export type TriagePriority = 'urgent' | 'high' | 'routine'

export function triagePriority(item: Pick<QueueItem, 'urgent' | 'risk_level'>): TriagePriority {
  if (item.urgent) return 'urgent'
  if (item.risk_level === 'critical' || item.risk_level === 'high') return 'high'
  return 'routine'
}
