import { ChevronDown, FileWarning, Scale } from 'lucide-react'
import { DOMAIN_META } from '../../lib/domains'
import { fieldLabel } from '../../lib/format'
import { CARD, cn } from '../../lib/styles'
import { ASSESSMENT_DOMAINS, type AssessmentDomain, type Inconsistency } from '../../types/api'

const SEVERITY_STYLES: Record<Inconsistency['severity'], string> = {
  high: 'bg-rose-50 text-rose-700 ring-rose-200',
  medium: 'bg-orange-50 text-orange-700 ring-orange-200',
  low: 'bg-slate-50 text-slate-600 ring-slate-200',
}

/** Contradictions to verify with the patient. Shown openly: they change how answers should be read. */
export function Inconsistencies({ items }: { items: Inconsistency[] }) {
  if (items.length === 0) return null
  return (
    <section aria-labelledby="inconsistencies-title" className={cn(CARD, 'p-5')}>
      <h3 id="inconsistencies-title" className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
        <Scale aria-hidden className="size-4 text-orange-500" />
        Needs verification
        <span className="text-xs font-normal text-slate-500">{items.length} contradictory answer{items.length === 1 ? '' : 's'}</span>
      </h3>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.code} className="flex items-start gap-3 rounded-xl border border-line px-3.5 py-2.5">
            <span className={cn('mt-0.5 rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ring-1 ring-inset', SEVERITY_STYLES[item.severity])}>
              {item.severity}
            </span>
            <div className="min-w-0 space-y-0.5">
              <p className="text-sm text-ink">{item.description}</p>
              <p className="text-xs text-slate-500">{item.domains.map((d) => DOMAIN_META[d].short).join(' · ')}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Missing required fields grouped by domain, in a collapsed accordion. */
export function MissingFields({ fields }: { fields: string[] }) {
  const byDomain = new Map<AssessmentDomain, string[]>()
  for (const path of fields) {
    const [domain, field] = path.split('.') as [AssessmentDomain, string]
    byDomain.set(domain, [...(byDomain.get(domain) ?? []), field])
  }
  const groups = ASSESSMENT_DOMAINS.filter((d) => byDomain.has(d))

  return (
    <details className={cn(CARD, 'group')}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2 text-sm font-semibold text-ink">
          <FileWarning aria-hidden className="size-4 text-amber-500" />
          Data quality
          <span className="text-xs font-normal text-slate-500">
            {fields.length === 0 ? 'All required fields answered' : `${fields.length} required field${fields.length === 1 ? '' : 's'} not answered`}
          </span>
        </span>
        <ChevronDown aria-hidden className="size-4 text-slate-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-line px-5 py-4">
        {groups.length === 0 ? (
          <p className="text-sm text-slate-500">Every required field across the 6 domains was answered.</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {groups.map((domain) => {
              const missing = byDomain.get(domain) ?? []
              return (
                <li key={domain} className="rounded-xl bg-slate-50 px-3.5 py-3">
                  <p className="text-sm font-medium text-ink">
                    {DOMAIN_META[domain].short} <span className="font-normal text-amber-700">({missing.length} missing)</span>
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500">{missing.map(fieldLabel).join(', ')}</p>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </details>
  )
}
