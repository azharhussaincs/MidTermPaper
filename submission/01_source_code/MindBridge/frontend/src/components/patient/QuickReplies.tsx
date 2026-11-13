import { useId } from 'react'
import type { QuickReplySet } from '../../lib/quickReplies'
import { cn } from '../../lib/styles'

interface QuickRepliesProps {
  set: QuickReplySet
  disabled: boolean
  onPick: (value: string) => void
}

/** One-tap answers that are sent immediately; the patient can always type a fuller answer instead. */
export function QuickReplies({ set, disabled, onPick }: QuickRepliesProps) {
  const labelId = useId()
  const isScale = set.kind === 'scale'
  return (
    <div role="group" aria-labelledby={labelId} className="min-w-0 flex-1 select-none">
      <span id={labelId} className="sr-only">
        {set.label}
      </span>
      <div className={cn('flex gap-1.5', isScale ? 'flex-nowrap overflow-x-auto pb-0.5' : 'flex-wrap')}>
        {set.options.map((option) => (
          <button
            key={option.value}
            type="button"
            disabled={disabled}
            onClick={() => onPick(option.value)}
            title={`Send “${option.value}”`}
            className={cn(
              'shrink-0 rounded-full border border-line bg-white text-sm font-medium text-slate-700 shadow-card transition-colors',
              'hover:border-teal-300 hover:bg-teal-50 hover:text-brand-strong',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
              'disabled:cursor-not-allowed disabled:opacity-50',
              isScale ? 'grid size-9 place-items-center tabular-nums' : 'h-8 px-3.5',
            )}
          >
            {option.label}
          </button>
        ))}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onPick("I'd rather not say")}
          title="Skip this question"
          className="h-8 shrink-0 rounded-full px-3 text-sm text-slate-400 hover:text-ink disabled:opacity-50"
        >
          Skip
        </button>
      </div>
    </div>
  )
}
