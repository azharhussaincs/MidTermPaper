import { AlertOctagon, AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import type { RiskAlert } from '../../lib/risk'
import { cn } from '../../lib/styles'

const ALERT_STYLES = {
  urgent: { box: 'border-rose-200 bg-rose-50', icon: 'text-rose-600', label: 'Urgent' },
  critical: { box: 'border-rose-200 bg-rose-50', icon: 'text-rose-600', label: 'Critical' },
  high: { box: 'border-orange-200 bg-orange-50/70', icon: 'text-orange-600', label: 'High' },
  elevated: { box: 'border-amber-200 bg-amber-50/60', icon: 'text-amber-600', label: 'Elevated' },
  none: { box: 'border-line bg-slate-50', icon: 'text-slate-500', label: 'Note' },
} as const

/** Areas requiring professional review, one card per distinct trigger (duplicates merged). */
export function RiskHighlights({ alerts }: { alerts: RiskAlert[] }) {
  if (alerts.length === 0) {
    return (
      <p className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800">
        <CheckCircle2 aria-hidden className="size-4" />
        No risk indicators were flagged in this intake.
      </p>
    )
  }
  return (
    <ul className="space-y-2">
      {alerts.map((alert) => {
        const style = ALERT_STYLES[alert.urgent ? 'urgent' : alert.level]
        const Icon = alert.urgent ? AlertOctagon : alert.level === 'elevated' ? Info : AlertTriangle
        return (
          <li key={alert.evidence} className={cn('flex gap-3 rounded-xl border px-3.5 py-3', style.box)}>
            <Icon aria-hidden className={cn('mt-0.5 size-5 shrink-0', style.icon)} />
            <div className="min-w-0 space-y-1">
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-semibold text-ink">
                <span className={cn('text-[11px] font-bold uppercase tracking-wider', style.icon)}>{style.label}</span>
                {alert.labels.join(' · ') || 'Flagged for review'}
              </p>
              <p className={cn('text-sm text-slate-700', alert.quoted && 'italic')}>
                {alert.quoted ? `“${alert.evidence}”` : alert.evidence.replaceAll('_', ' ').replaceAll('=', ': ')}
              </p>
              {alert.action && <p className="text-xs font-medium text-rose-700">{alert.action}</p>}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
