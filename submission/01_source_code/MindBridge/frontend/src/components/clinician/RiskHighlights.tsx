import { AlertOctagon, AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import type { RiskAlert } from '../../lib/risk'
import { cn } from '../../lib/styles'

// Only urgent/critical items get a tinted surface; the rest stay white with a coloured edge.
const ALERT_STYLES = {
  urgent: { box: 'bg-rose-50 ring-rose-200 before:bg-rose-500', icon: 'text-rose-600', label: 'Urgent', labelText: 'text-rose-700' },
  critical: { box: 'bg-rose-50 ring-rose-200 before:bg-rose-500', icon: 'text-rose-600', label: 'Critical', labelText: 'text-rose-700' },
  high: { box: 'bg-white ring-line/70 before:bg-orange-400', icon: 'text-orange-600', label: 'High', labelText: 'text-orange-700' },
  elevated: { box: 'bg-white ring-line/70 before:bg-amber-300', icon: 'text-amber-600', label: 'Elevated', labelText: 'text-amber-700' },
  none: { box: 'bg-white ring-line/70 before:bg-slate-300', icon: 'text-muted', label: 'Note', labelText: 'text-muted' },
} as const

/** Areas requiring professional review: one compact card per risk type (duplicates merged). */
export function RiskHighlights({ alerts, onShowEvidence }: { alerts: RiskAlert[]; onShowEvidence?: (quote: string) => void }) {
  if (alerts.length === 0) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted">
        <CheckCircle2 aria-hidden className="size-4 text-emerald-600" />
        No risk indicators in this check-in.
      </p>
    )
  }
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {alerts.map((alert) => {
        const style = ALERT_STYLES[alert.urgent ? 'urgent' : alert.level]
        const Icon = alert.urgent ? AlertOctagon : alert.level === 'elevated' ? Info : AlertTriangle
        const reason = alert.quoted ? `“${alert.evidence[0]}”` : alert.evidence[0]
        const all = alert.evidence.map((e) => (alert.quoted ? `“${e}”` : e)).join('\n')
        return (
          <li
            key={alert.label}
            className={cn(
              'relative flex min-w-0 items-start gap-3 overflow-hidden rounded-xl py-3 pr-4 pl-5 shadow-card ring-1',
              'before:absolute before:inset-y-0 before:left-0 before:w-1',
              style.box,
            )}
          >
            <Icon aria-hidden className={cn('mt-0.5 size-4 shrink-0', style.icon)} />
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                <span className="truncate">{alert.label}</span>
                <span className={cn('shrink-0 text-[11px] font-bold uppercase tracking-wide', style.labelText)}>{style.label}</span>
                {alert.evidence.length > 1 && (
                  <span className="ml-auto shrink-0 text-xs font-medium tabular-nums text-muted" title={`${alert.evidence.length} separate mentions`}>
                    ×{alert.evidence.length}
                  </span>
                )}
              </p>
              <p title={all} className={cn('mt-1 truncate text-[13px] text-muted', alert.quoted && 'italic')}>
                {reason}
              </p>
              {/* Safety instruction: always visible, never only in a tooltip. */}
              {alert.action && <p className="mt-1.5 text-xs font-semibold text-rose-700">{alert.action}</p>}
              {alert.quoted && onShowEvidence && (
                <button
                  type="button"
                  onClick={() => onShowEvidence(alert.evidence[0])}
                  className="mt-1.5 text-xs font-medium text-brand-strong underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-brand"
                >
                  See in conversation
                </button>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
