import { ClipboardList, Inbox } from 'lucide-react'
import type { ReactNode } from 'react'
import { timeAgo } from '../../lib/format'
import { riskLabel, triagePriority, type TriagePriority } from '../../lib/risk'
import { cn } from '../../lib/styles'
import type { QueueItem } from '../../types/api'
import { ErrorNotice } from '../ui'

export type QueueFilter = 'awaiting' | 'reviewed'

const PRIORITY: Record<TriagePriority, { label: string; border: string; text: string }> = {
  urgent: { label: 'Urgent', border: 'border-l-rose-500', text: 'text-rose-600' },
  high: { label: 'High', border: 'border-l-amber-500', text: 'text-amber-600' },
  routine: { label: 'Routine', border: 'border-l-teal-500', text: 'text-teal-700' },
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
    <aside className="flex flex-col border-b border-line bg-white lg:min-h-0 lg:border-r lg:border-b-0">
      <div className="space-y-3 border-b border-line px-4 py-4">
        <div className="flex items-center justify-between">
          <h1 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <ClipboardList aria-hidden className="size-4 text-accent" />
            Triage queue
          </h1>
          <span className="text-xs text-slate-500">Highest priority first</span>
        </div>
        {/* A filter over one list: toggle buttons (aria-pressed), not tabs. */}
        <div role="group" aria-label="Queue filter" className="grid grid-cols-2 rounded-xl bg-slate-100 p-1">
          <FilterButton active={filter === 'awaiting'} onClick={() => onFilterChange('awaiting')}>
            Awaiting <Count n={awaiting.length} highlight={filter === 'awaiting'} />
          </FilterButton>
          <FilterButton active={filter === 'reviewed'} onClick={() => onFilterChange('reviewed')}>
            Reviewed <Count n={reviewed.length} highlight={filter === 'reviewed'} />
          </FilterButton>
        </div>
        {error && <ErrorNotice message={error} />}
      </div>

      <ul className="max-h-[22rem] space-y-2 overflow-y-auto p-3 lg:max-h-none lg:flex-1">
        {items.length === 0 && (
          <li className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-slate-500">
            <Inbox aria-hidden className="size-6 text-slate-300" />
            {filter === 'awaiting' ? 'All caught up. No intakes are waiting for review.' : 'No reviewed intakes yet.'}
          </li>
        )}
        {items.map((item) => (
          <li key={item.session_id}>
            <TriageCard item={item} selected={item.session_id === selectedId} onSelect={() => onSelect(item.session_id)} />
          </li>
        ))}
      </ul>
    </aside>
  )
}

function Count({ n, highlight }: { n: number; highlight: boolean }) {
  return (
    <span className={cn('ml-1 rounded-full px-1.5 text-[11px] tabular-nums', highlight ? 'bg-indigo-50 text-accent' : 'bg-slate-200 text-slate-600')}>
      {n}
    </span>
  )
}

function FilterButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'h-8 rounded-lg text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-brand',
        active ? 'bg-white text-ink shadow-card' : 'text-slate-500 hover:text-ink',
      )}
    >
      {children}
    </button>
  )
}

function TriageCard({ item, selected, onSelect }: { item: QueueItem; selected: boolean; onSelect: () => void }) {
  const priority = PRIORITY[triagePriority(item)]
  const reviewed = item.status === 'reviewed'
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      className={cn(
        'w-full rounded-xl border border-l-4 bg-white p-3 text-left transition-shadow',
        'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand',
        priority.border,
        selected ? 'border-y-indigo-200 border-r-indigo-200 bg-indigo-50/40 shadow-card' : 'border-y-line border-r-line hover:shadow-card',
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <span className={cn('text-[11px] font-bold uppercase tracking-wider', priority.text)}>{priority.label}</span>
        <span className="text-[11px] text-slate-400">
          {reviewed ? `Reviewed ${timeAgo(item.updated_at)}` : timeAgo(item.created_at)}
        </span>
      </span>
      <span className="mt-1 flex items-center justify-between gap-2">
        <span className="truncate text-sm font-semibold text-ink">{item.patient_alias ?? 'anonymous'}</span>
        <span className="text-xs font-medium tabular-nums text-slate-500">{Math.round(item.completion_pct)}%</span>
      </span>
      {item.top_risk_flags.length > 0 && (
        <span className="mt-1 block truncate text-xs text-slate-500">{[...new Set(item.top_risk_flags.map(riskLabel))].join(' · ')}</span>
      )}
      <span className="mt-2 flex flex-wrap gap-1">
        {item.early_submission && <Tag>Submitted early</Tag>}
        {reviewed && <Tag tone={item.clinician_approved ? 'ok' : 'warn'}>{item.clinician_approved ? 'Signed off' : 'Follow-up requested'}</Tag>}
      </span>
    </button>
  )
}

function Tag({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'ok' | 'warn' }) {
  return (
    <span
      className={cn(
        'rounded-md px-1.5 py-0.5 text-[11px] font-medium',
        tone === 'ok' && 'bg-emerald-50 text-emerald-700',
        tone === 'warn' && 'bg-amber-50 text-amber-800',
        tone === 'neutral' && 'bg-slate-100 text-slate-600',
      )}
    >
      {children}
    </span>
  )
}
