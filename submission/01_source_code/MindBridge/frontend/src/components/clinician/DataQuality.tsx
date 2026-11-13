import { ArrowLeftRight, CheckCircle2 } from 'lucide-react'
import { DOMAIN_META } from '../../lib/domains'
import { fieldLabel } from '../../lib/format'
import { cn } from '../../lib/styles'
import { ASSESSMENT_DOMAINS, type AssessmentDomain, type Inconsistency } from '../../types/api'

const SEVERITY_STYLES: Record<Inconsistency['severity'], string> = {
  high: 'text-rose-700',
  medium: 'text-orange-700',
  low: 'text-muted',
}

/**
 * "Reported stress 0/10 but also frequent panic attacks, 2h sleep." -> ["Stress 0/10", "Frequent panic attacks, 2h sleep"].
 * Null when the description doesn't follow the "X but Y" shape (backend/app/services/assessment_audit.py).
 */
function splitContradiction(description: string): [string, string] | null {
  const match =
    /^(.*?)\s+but\s+(?:also\s+)?(?:reported\s+)?(.*?)\.?$/i.exec(description) ?? /^(Rated .*?)\s+on\s+(.*?)\.?$/i.exec(description)
  if (!match) return null
  const left = match[1].replace(/^(Reported|Rated|Said they have)\s+/i, '').replace(/^\w/, (c) => c.toUpperCase())
  const right = match[2].replace(/^\w/, (c) => c.toUpperCase())
  return [left, right]
}

/** Contradictions to verify with the patient. Shown openly: they change how answers should be read. */
export function Inconsistencies({ items }: { items: Inconsistency[] }) {
  if (items.length === 0) return null
  return (
    <ul className="divide-y divide-line/70 overflow-hidden rounded-2xl bg-white shadow-card ring-1 ring-line/70">
      {items.map((item) => {
        const pair = splitContradiction(item.description)
        return (
          <li key={item.code} title={item.description} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3.5">
            <span className={cn('w-14 shrink-0 text-[11px] font-bold uppercase tracking-wide', SEVERITY_STYLES[item.severity])}>
              {item.severity}
            </span>
            {pair ? (
              <span className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-sm">
                <span className="font-medium text-ink">{pair[0]}</span>
                <ArrowLeftRight aria-label="versus" className="size-3.5 shrink-0 text-orange-500" />
                <span className="text-orange-900">{pair[1]}</span>
              </span>
            ) : (
              <span className="min-w-0 flex-1 text-sm text-ink">{item.description}</span>
            )}
            <span className="text-xs text-muted">{item.domains.map((d) => DOMAIN_META[d].short).join(' · ')}</span>
          </li>
        )
      })}
    </ul>
  )
}

/** Unanswered required questions, grouped by topic. */
export function MissingFields({ fields }: { fields: string[] }) {
  const byDomain = new Map<AssessmentDomain, string[]>()
  for (const path of fields) {
    const [domain, field] = path.split('.') as [AssessmentDomain, string]
    byDomain.set(domain, [...(byDomain.get(domain) ?? []), field])
  }
  const groups = ASSESSMENT_DOMAINS.filter((d) => byDomain.has(d))

  if (groups.length === 0) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted">
        <CheckCircle2 aria-hidden className="size-4 text-emerald-600" />
        Every required question was answered.
      </p>
    )
  }
  return (
    <ul className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
      {groups.map((domain) => {
        const missing = byDomain.get(domain) ?? []
        const Icon = DOMAIN_META[domain].icon
        return (
          <li key={domain} className="flex gap-3">
            <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-slate-400" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">
                {DOMAIN_META[domain].title} <span className="font-normal text-muted">· {missing.length} not answered</span>
              </p>
              <p className="mt-0.5 text-[13px] leading-relaxed text-muted">{missing.map(fieldLabel).join(', ')}</p>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
