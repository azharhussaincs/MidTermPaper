import type { AssessmentDomain, AssessmentStatusName, RiskLevel } from '../types/api'

export const DOMAIN_LABELS: Record<AssessmentDomain, string> = {
  mood: 'Mood & Emotional Wellbeing',
  stress: 'Stress Levels',
  sleep: 'Sleep Patterns',
  anxiety: 'Anxiety Experiences',
  functioning: 'Daily Functioning',
  concerns: 'Personal Concerns',
}

export const STATUS_LABELS: Record<AssessmentStatusName, string> = {
  in_progress: 'In Progress',
  interrupted: 'Interrupted',
  awaiting_clinician_review: 'Awaiting Clinician Review',
  reviewed: 'Reviewed',
}

export const RISK_LABELS: Record<RiskLevel, string> = {
  critical: 'Critical',
  high: 'High',
  elevated: 'Elevated',
  none: 'No flags',
}

const FREQUENCY = ['Not at all', 'Several days', 'More than half the days', 'Nearly every day']

/** Human-readable labels for stored domain fields (backend/app/schemas/assessment.py). */
export const FIELD_LABELS: Record<string, string> = {
  phq_little_interest: 'Little interest or pleasure',
  phq_feeling_down: 'Feeling down or hopeless',
  overall_mood_rating: 'Self-rated mood',
  hopelessness_level: 'Hopelessness',
  self_harm_thoughts: 'Thoughts of self-harm',
  who5_items: 'WHO-5 wellbeing items',
  mood_description: 'Mood in their words',
  perceived_stress_level: 'Perceived stress',
  stress_triggers: 'Stress triggers',
  stress_duration: 'Duration',
  feels_overwhelmed: 'Feels overwhelmed',
  coping_strategies: 'Coping strategies',
  average_sleep_hours: 'Average sleep',
  sleep_quality: 'Sleep quality',
  reports_sleep_problems: 'Reports sleep problems',
  difficulty_falling_asleep: 'Difficulty falling asleep',
  frequent_night_waking: 'Frequent night waking',
  early_morning_waking: 'Early morning waking',
  wakes_unrefreshed: 'Wakes unrefreshed',
  excessive_daytime_sleepiness: 'Daytime sleepiness',
  sleeping_more_than_usual: 'Sleeping more than usual',
  gad_nervous_anxious: 'Nervous, anxious or on edge',
  gad_uncontrollable_worry: 'Unable to control worrying',
  panic_attacks: 'Panic attacks',
  physical_symptoms: 'Physical symptoms',
  cognitive_symptoms: 'Cognitive symptoms',
  avoidance_behaviours: 'Avoidance',
  work_study_impact: 'Impact on work/study',
  social_engagement: 'Social engagement',
  energy_level: 'Energy level',
  self_care: 'Self-care',
  days_missed_last_month: 'Days missed (last month)',
  narrative: 'In their own words',
  main_challenges: 'Main challenges',
  support_goals: 'Support goals',
  currently_receiving_support: 'Currently receiving support',
  notes: 'Notes',
}

const FREQUENCY_FIELDS = new Set([
  'phq_little_interest',
  'phq_feeling_down',
  'gad_nervous_anxious',
  'gad_uncontrollable_worry',
])

export function humanize(value: string): string {
  const text = value.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? humanize(field)
}

/** "mood.phq_feeling_down" -> "Mood: Feeling down or hopeless" */
export function missingFieldLabel(path: string): string {
  const [domain, field = ''] = path.split('.')
  return `${humanize(domain)}: ${fieldLabel(field)}`
}

export function formatFieldValue(field: string, value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (FREQUENCY_FIELDS.has(field) && typeof value === 'number') return `${FREQUENCY[value] ?? value} (${value}/3)`
  if (field === 'overall_mood_rating' || field === 'energy_level') return `${value}/10`
  if (field === 'perceived_stress_level') return `${value}/10`
  if (field === 'average_sleep_hours') return `${value} h/night`
  if (field === 'who5_items' && Array.isArray(value)) {
    const total = value.reduce((sum: number, n) => sum + Number(n), 0)
    return `${value.join(', ')} (index ${total * 4}/100)`
  }
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  if (typeof value === 'string') return /^[a-z_]+$/.test(value) ? humanize(value) : value
  return String(value)
}

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
const dateTimeFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

export function formatTime(iso: string | null | undefined): string {
  return iso ? timeFormat.format(new Date(iso)) : ''
}

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTimeFormat.format(new Date(iso)) : ''
}

export function timeAgo(iso: string, now = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return relative.format(Math.trunc(seconds / size), unit)
  }
  return 'just now'
}

/** Splits "[M1] text" into its tag and text. */
export function splitTag(entry: string): { tag: string | null; kind: 'M' | 'I' | 'R' | null; text: string } {
  const match = /^\[([MIR])(\d+)\]\s*(.*)$/s.exec(entry)
  if (!match) return { tag: null, kind: null, text: entry }
  return { tag: `${match[1]}${match[2]}`, kind: match[1] as 'M' | 'I' | 'R', text: match[3] }
}
