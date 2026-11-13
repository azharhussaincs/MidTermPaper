import { CheckCircle2, Inbox } from 'lucide-react'
import type { ReactNode } from 'react'
import { timeAgo } from '../../lib/format'
import { riskLabel, triagePriority, type TriagePriority } from '../../lib/risk'
import { cn } from '../../lib/styles'
import type { QueueItem } from '../../types/api'
import { ErrorNotice } from '../ui'

export type QueueFilter = 'awaiting' | 'reviewed'

const PRIORITY: Record<TriagePriority, { label: string; text: string; dot: string; edge: string }> = {
  urgent: { label: 'Urgent', text: 'text-rose-700', dot: 'bg-rose-500', edge: 'before:bg-rose-500' },
  high: { label: 'High priority', text: 'text-amber-800', dot: 'bg-amber-500', edge: 'before:bg-amber-400' },
  routine: { label: 'Routine', text: 'text-muted', dot: 'bg-slate-300', edge: 'before:bg-transparent' },
}

interface TriageQueueProps {
  awaiting: QueueItem[]
  reviewed: QueueItem[]
  filter: QueueFilter
  onFilterChange: (filter: QueueFilter) => void
  selectedId: string | null
  onSelect: (id: string) => void
  error: string | null
}

export function TriageQueue({ awaiting, reviewed, filter, onFilterChange, selectedId, onSelect, error }: TriageQueueProps) {
  const items = filter === 'awaiting' ? awaiting : reviewed
  return (
    <aside className="flex flex-col border-b border-line/80 lg:min-h-0 lg:border-r lg:border-b-0">
      <div className="px-5 pt-7 sm:px-6">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">Review queue</h1>
        <p className="mt-1 text-sm leading-relaxed text-muted">Check-ins prepared by the AI screening, most urgent first.</p>

        {/* A filter over one list: toggle buttons (aria-pressed), not tabs. */}
        <div role="group" aria-label="Queue filter" className="mt-5 flex gap-6 border-b border-line">
          <FilterButton active={filter === 'awaiting'} onClick={() => onFilterChange('awaiting')}>
            Waiting <Count n={awaiting.length} />
          </FilterButton>
          <FilterButton active={filter === 'reviewed'} onClick={() => onFilterChange('reviewed')}>
            Reviewed <Count n={reviewed.length} />
          </FilterButton>
        </div>
        {error && (
          <div className="mt-3">
            <ErrorNotice message={error} />
          </div>
        )}
      </div>

      <ul className="max-h-[24rem] divide-y divide-line/70 overflow-y-auto lg:max-h-none lg:flex-1">
        {items.length === 0 && (
          <li className="flex flex-col items-center gap-2 px-6 py-14 text-center">
            <span className="grid size-11 place-items-center rounded-full bg-brand-soft text-brand-strong">
              {filter === 'awaiting' ? <CheckCircle2 aria-hidden className="size-5" /> : <Inbox aria-hidden className="size-5" />}
            </span>
            <span className="mt-1 font-display text-lg font-semibold text-ink">{filter === 'awaiting' ? 'All caught up' : 'Nothing reviewed yet'}</span>
            <span className="max-w-[16rem] text-sm text-muted">
              {filter === 'awaiting' ? 'New check-ins appear here as soon as patients submit them.' : 'Check-ins you sign off will be listed here.'}
            </span>
          </li>
        )}
        {items.map((item) => (
          <li key={item.session_id}>
            <QueueRow item={item} selected={item.session_id === selectedId} onSelect={() => onSelect(item.session_id)} />
          </li>
        ))}
      </ul>
    </aside>
  )
}

function Count({ n }: { n: number }) {
  return <span className="ml-1 text-xs font-semibold tabular-nums text-muted">{n}</span>
}

function FilterButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        '-mb-px border-b-2 pb-2.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        active ? 'border-brand text-ink' : 'border-transparent text-muted hover:text-ink',
      )}
    >
      {children}
    </button>
  )
}

function QueueRow({ item, selected, onSelect }: { item: QueueItem; selected: boolean; onSelect: () => void }) {
  const priority = PRIORITY[triagePriority(item)]
  const reviewed = item.status === 'reviewed'
  const percent = Math.round(item.completion_pct)
  const concerns = [...new Set(item.top_risk_flags.map(riskLabel))]
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      className={cn(
        // Edge marker carries priority; the selected row is lifted onto a white surface.
        'relative block w-full px-5 py-4 text-left transition-colors sm:px-6',
        'before:absolute before:inset-y-3 before:left-0 before:w-[3px] before:rounded-r-full',
        priority.edge,
        'focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand',
        selected ? 'bg-white shadow-card' : 'hover:bg-white/60',
      )}
    >
      <span className="flex items-baseline justify-between gap-3">
        <span className="truncate text-[15px] font-semibold text-ink">{item.patient_alias ?? 'anonymous'}</span>
        <span className="shrink-0 text-xs text-muted">{reviewed ? `Reviewed ${timeAgo(item.updated_at)}` : timeAgo(item.created_at)}</span>
      </span>
      <span className="mt-1 block truncate text-[13px] text-muted">{concerns.length > 0 ? concerns.join(' · ') : 'No risk flags'}</span>
      <span className="mt-2.5 flex items-center gap-3 text-xs">
        <span className={cn('inline-flex items-center gap-1.5 font-semibold', priority.text)}>
          <span aria-hidden className={cn('size-1.5 rounded-full', priority.dot)} />
          {priority.label}
        </span>
        <span className="text-muted tabular-nums" title={`${percent}% of questions answered`}>
          {percent}% answered
        </span>
        {item.early_submission && <span className="text-muted">Sent early</span>}
        {reviewed && (
          <span className={cn('ml-auto font-medium', item.clinician_approved ? 'text-emerald-700' : 'text-amber-800')}>
            {item.clinician_approved ? 'Signed off' : 'Follow-up'}
          </span>
        )}
      </span>
    </button>
  )
}
