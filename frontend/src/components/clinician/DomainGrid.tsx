import type { ReactNode } from 'react'
import { DOMAIN_META } from '../../lib/domains'
import { fieldLabel, humanize } from '../../lib/format'
import { FREQUENCY_OPTIONS } from '../../lib/quickReplies'
import { CARD, cn } from '../../lib/styles'
import { ASSESSMENT_DOMAINS, type AssessmentDomainData, type DomainProgress, type AssessmentDomain } from '../../types/api'
import { Meter } from '../ui'

type Tone = 'ok' | 'mild' | 'warn' | 'danger' | 'neutral'

const TONE_PILL: Record<Tone, string> = {
  ok: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  mild: 'bg-amber-50 text-amber-700 ring-amber-200',
  warn: 'bg-orange-50 text-orange-700 ring-orange-200',
  danger: 'bg-rose-50 text-rose-700 ring-rose-200',
  neutral: 'bg-slate-50 text-slate-700 ring-slate-200',
}

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
  return (
    <span className={cn('inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset', TONE_PILL[tone])}>
      {children}
    </span>
  )
}

function FieldValue({ field, value }: { field: string; value: unknown }) {
  if (field in SCALE_FIELDS && typeof value === 'number') {
    const bad = SCALE_FIELDS[field] === 'high_is_bad' ? value >= 8 : value <= 3
    const watch = SCALE_FIELDS[field] === 'high_is_bad' ? value >= 5 : value <= 5
    return (
      <div className="w-28">
        <Meter label={fieldLabel(field)} hideLabel value={value} max={10} tone={bad ? 'danger' : watch ? 'warn' : 'complete'} />
        <span className="text-xs font-semibold tabular-nums text-ink">{value}/10</span>
      </div>
    )
  }
  if (FREQUENCY_FIELDS.has(field) && typeof value === 'number') {
    const tone: Tone = (['ok', 'mild', 'warn', 'danger'] as const)[value] ?? 'neutral'
    return (
      <Pill tone={tone}>
        {FREQUENCY_OPTIONS[value]} · {value}/3
      </Pill>
    )
  }
  if (field === 'average_sleep_hours' && typeof value === 'number') {
    return (
      <div className="w-28">
        <Meter label={fieldLabel(field)} hideLabel value={Math.min(value, 12)} max={12} tone={value < 4 ? 'danger' : value < 6 ? 'warn' : 'complete'} />
        <span className="text-xs font-semibold tabular-nums text-ink">{value} h / night</span>
      </div>
    )
  }
  if (field === 'who5_items' && Array.isArray(value)) {
    const index = value.reduce((sum: number, n) => sum + Number(n), 0) * 4
    return <Pill tone={index <= 28 ? 'danger' : index <= 50 ? 'warn' : 'ok'}>WHO-5 index {index}/100</Pill>
  }
  if (typeof value === 'boolean') {
    return <Pill tone={value && CONCERNING_YES.has(field) ? 'danger' : 'neutral'}>{value ? 'Yes' : 'No'}</Pill>
  }
  if (typeof value === 'string' && value in SEVERITY_TONE) {
    return <Pill tone={SEVERITY_TONE[value]}>{humanize(value)}</Pill>
  }
  if (Array.isArray(value)) {
    return (
      <span className="flex flex-wrap justify-end gap-1">
        {value.map((item) => (
          <span key={String(item)} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">
            {String(item)}
          </span>
        ))}
      </span>
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
    <section aria-labelledby={`domain-${domain}`} className={cn(CARD, 'flex flex-col p-4')}>
      <header className="mb-3 flex items-center justify-between gap-2">
        <h4 id={`domain-${domain}`} className="flex items-center gap-2 text-sm font-semibold text-ink">
          <span className="grid size-7 place-items-center rounded-lg bg-teal-50 text-brand">
            <Icon aria-hidden className="size-4" />
          </span>
          {meta.title}
        </h4>
        {progress && (
          <span className={cn('text-[11px] font-semibold tabular-nums', progress.completed ? 'text-emerald-600' : 'text-slate-400')}>
            {progress.answered}/{progress.required} required
          </span>
        )}
      </header>

      {entries.length === 0 ? (
        <p className="grid flex-1 place-items-center rounded-xl border border-dashed border-line py-6 text-xs text-slate-400">
          Not yet reported
        </p>
      ) : (
        <div className="space-y-3">
          {structured.length > 0 && (
            <dl className="divide-y divide-line">
              {structured.map(([field, value]) => (
                <div key={field} className="flex items-center justify-between gap-3 py-2 first:pt-0">
                  <dt className="text-xs text-slate-500">{fieldLabel(field)}</dt>
                  <dd className="text-right">
                    <FieldValue field={field} value={value} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {narrative.map(([field, value]) => (
            <blockquote key={field} className="rounded-xl bg-slate-50 px-3 py-2 text-sm italic text-slate-700">
              <span className="mb-0.5 block text-[11px] font-semibold uppercase not-italic tracking-wider text-slate-400">
                {fieldLabel(field)}
              </span>
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
