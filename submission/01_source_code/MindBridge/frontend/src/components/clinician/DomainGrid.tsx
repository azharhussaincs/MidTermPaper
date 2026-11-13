import type { ReactNode } from 'react'
import { DOMAIN_META } from '../../lib/domains'
import { fieldLabel, humanize } from '../../lib/format'
import { FREQUENCY_OPTIONS } from '../../lib/quickReplies'
import { cn } from '../../lib/styles'
import { ASSESSMENT_DOMAINS, type AssessmentDomainData, type DomainProgress, type AssessmentDomain } from '../../types/api'

type Tone = 'ok' | 'mild' | 'warn' | 'danger' | 'neutral'

// Values read as text, not pills: only concerning answers get colour and a dot.
const TONE_TEXT: Record<Tone, string> = {
  ok: 'text-ink',
  mild: 'text-amber-800',
  warn: 'text-orange-800',
  danger: 'text-rose-700',
  neutral: 'text-ink',
}
const TONE_DOT: Partial<Record<Tone, string>> = { mild: 'bg-amber-400', warn: 'bg-orange-500', danger: 'bg-rose-500' }

const SEVERITY_TONE: Record<string, Tone> = {
  none: 'ok', mild: 'mild', moderate: 'warn', severe: 'danger',
  occasional: 'mild', frequent: 'warn',
  very_poor: 'danger', poor: 'warn', fair: 'mild', good: 'ok', very_good: 'ok',
  normal: 'ok', reduced: 'mild', minimal: 'warn', isolated: 'danger',
  maintained: 'ok', somewhat_neglected: 'warn', significantly_neglected: 'danger',
}  // fmt: skip

/** 0-10 scales: which end is concerning. */
const SCALE_FIELDS: Record<string, 'high_is_bad' | 'low_is_bad'> = {
  perceived_stress_level: 'high_is_bad',
  overall_mood_rating: 'low_is_bad',
  energy_level: 'low_is_bad',
}
const FREQUENCY_FIELDS = new Set(['phq_little_interest', 'phq_feeling_down', 'gad_nervous_anxious', 'gad_uncontrollable_worry'])
const CONCERNING_YES = new Set(['self_harm_thoughts', 'feels_overwhelmed', 'avoidance_behaviours'])
const TEXT_FIELDS = new Set(['mood_description', 'notes', 'narrative'])

function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  const dot = TONE_DOT[tone]
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-[13px] font-medium whitespace-nowrap', TONE_TEXT[tone])}>
      {dot && <span aria-hidden className={cn('size-1.5 rounded-full', dot)} />}
      {children}
    </span>
  )
}

/** Bar + value on one line. The row's <dt> already names the field, so the bar itself is decorative. */
function ScaleValue({ value, max, text, tone }: { value: number; max: number; text: string; tone: 'danger' | 'warn' | 'complete' }) {
  return (
    <span className="flex items-center justify-end gap-2">
      <progress aria-hidden className={cn('meter w-16', tone)} max={max} value={Math.min(value, max)} />
      <span className="w-12 text-right text-xs font-semibold tabular-nums text-ink">{text}</span>
    </span>
  )
}

function FieldValue({ field, value }: { field: string; value: unknown }) {
  if (field in SCALE_FIELDS && typeof value === 'number') {
    const bad = SCALE_FIELDS[field] === 'high_is_bad' ? value >= 8 : value <= 3
    const watch = SCALE_FIELDS[field] === 'high_is_bad' ? value >= 5 : value <= 5
    return <ScaleValue value={value} max={10} text={`${value}/10`} tone={bad ? 'danger' : watch ? 'warn' : 'complete'} />
  }
  if (FREQUENCY_FIELDS.has(field) && typeof value === 'number') {
    const tone: Tone = (['ok', 'mild', 'warn', 'danger'] as const)[value] ?? 'neutral'
    return (
      <span title={`${value}/3`}>
        <Pill tone={tone}>{FREQUENCY_OPTIONS[value]}</Pill>
      </span>
    )
  }
  if (field === 'average_sleep_hours' && typeof value === 'number') {
    return <ScaleValue value={value} max={12} text={`${value} h`} tone={value < 4 ? 'danger' : value < 6 ? 'warn' : 'complete'} />
  }
  if (field === 'who5_items' && Array.isArray(value)) {
    const index = value.reduce((sum: number, n) => sum + Number(n), 0) * 4
    return <Pill tone={index <= 28 ? 'danger' : index <= 50 ? 'warn' : 'ok'}>{index}/100</Pill>
  }
  if (typeof value === 'boolean') {
    return <Pill tone={value && CONCERNING_YES.has(field) ? 'danger' : 'neutral'}>{value ? 'Yes' : 'No'}</Pill>
  }
  if (typeof value === 'string' && value in SEVERITY_TONE) {
    return <Pill tone={SEVERITY_TONE[value]}>{humanize(value)}</Pill>
  }
  if (Array.isArray(value)) {
    return (
      <span className="text-[13px] text-ink">{value.map(String).join(', ')}</span>
    )
  }
  if (typeof value === 'number') return <span className="text-sm font-semibold tabular-nums text-ink">{value}</span>
  return <span className="text-sm text-ink">{humanize(String(value))}</span>
}

function DomainCard({ domain, answers, progress }: { domain: AssessmentDomain; answers: Record<string, unknown>; progress?: DomainProgress }) {
  const meta = DOMAIN_META[domain]
  const Icon = meta.icon
  const entries = Object.entries(answers).filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0))
  const structured = entries.filter(([field]) => !TEXT_FIELDS.has(field))
  const narrative = entries.filter(([field]) => TEXT_FIELDS.has(field))

  return (
    <section aria-labelledby={`domain-${domain}`} className="flex flex-col rounded-2xl bg-white p-5 shadow-card ring-1 ring-line/70">
      <header className="mb-3 flex items-center justify-between gap-2">
        <h4 id={`domain-${domain}`} className="flex items-center gap-2 text-sm font-semibold text-ink">
          <span className="grid size-7 place-items-center rounded-lg bg-teal-50 text-brand">
            <Icon aria-hidden className="size-4" />
          </span>
          {meta.title}
        </h4>
        {progress && (
          <span
            title="Required fields answered"
            className={cn('text-xs font-semibold tabular-nums', progress.completed ? 'text-emerald-600' : 'text-slate-400')}
          >
            {progress.answered}/{progress.required}
          </span>
        )}
      </header>

      {entries.length === 0 ? (
        <p className="text-sm text-slate-400">Not yet reported</p>
      ) : (
        <div className="space-y-3">
          {structured.length > 0 && (
            <dl className="divide-y divide-line">
              {structured.map(([field, value]) => (
                <div key={field} className="flex items-center justify-between gap-3 py-2 first:pt-0">
                  <dt className="text-xs text-muted">{fieldLabel(field)}</dt>
                  <dd className="text-right">
                    <FieldValue field={field} value={value} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {narrative.map(([field, value]) => (
            <blockquote key={field} title={fieldLabel(field)} className="rounded-xl bg-slate-50 px-3 py-2 text-sm italic text-slate-700">
              “{String(value)}”
            </blockquote>
          ))}
        </div>
      )}
    </section>
  )
}

interface DomainGridProps {
  data: AssessmentDomainData
  progress: Partial<Record<AssessmentDomain, DomainProgress>>
}

/** The 6 domains as a 2×3 grid of self-reported answers with visual scales. */
export function DomainGrid({ data, progress }: DomainGridProps) {
  return (
    // Container queries: columns follow the dossier's own width (2×3 on a typical desktop).
    <div className="@container">
      <div className="grid gap-4 @2xl:grid-cols-2 @5xl:grid-cols-3">
        {ASSESSMENT_DOMAINS.map((domain) => (
          <DomainCard key={domain} domain={domain} answers={(data[domain] ?? {}) as Record<string, unknown>} progress={progress[domain]} />
        ))}
      </div>
    </div>
  )
}
