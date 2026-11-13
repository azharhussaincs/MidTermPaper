import { Check } from 'lucide-react'
import { DOMAIN_META } from '../../lib/domains'
import { cn } from '../../lib/styles'
import { ASSESSMENT_DOMAINS, type AssessmentDomain, type DomainProgress } from '../../types/api'

interface DomainStepperProps {
  progress: Partial<Record<AssessmentDomain, DomainProgress>>
}

/** 1. Mood → 2. Stress → 3. Sleep → 4. Anxiety → 5. Daily Life → 6. Goals */
export function DomainStepper({ progress }: DomainStepperProps) {
  const current = ASSESSMENT_DOMAINS.find((domain) => !progress[domain]?.completed)
  const done = ASSESSMENT_DOMAINS.filter((domain) => progress[domain]?.completed).length

  return (
    <nav aria-label={`Topics: ${done} of 6 done`}>
      <ol className="flex items-center gap-[3px] sm:gap-0">
        {ASSESSMENT_DOMAINS.map((domain, index) => {
          const meta = DOMAIN_META[domain]
          const state = progress[domain]?.completed ? 'done' : domain === current ? 'current' : 'todo'
          const Icon = meta.icon
          return (
            <li key={domain} className="flex items-center" aria-current={state === 'current' ? 'step' : undefined}>
              {index > 0 && (
                <span
                  aria-hidden
                  className={cn('mx-1 hidden h-px w-3 sm:block lg:w-5', progress[ASSESSMENT_DOMAINS[index - 1]]?.completed ? 'bg-brand' : 'bg-line')}
                />
              )}
              <span
                title={`${index + 1}. ${meta.title}${state === 'done' ? ' · done' : state === 'current' ? ' · now' : ''}`}
                className={cn(
                  'flex items-center gap-1.5 rounded-full text-xs font-medium transition-colors sm:py-1 sm:pr-2.5 sm:pl-1',
                  state === 'current' && 'bg-teal-50 text-brand-strong ring-1 ring-teal-200',
                  state === 'done' && 'text-ink',
                  state === 'todo' && 'text-slate-400',
                )}
              >
                <span
                  className={cn(
                    'grid size-6 place-items-center rounded-full',
                    state === 'done' && 'bg-brand text-white',
                    state === 'current' && 'bg-white text-brand shadow-card',
                    state === 'todo' && 'bg-slate-100',
                  )}
                >
                  {state === 'done' ? <Check aria-hidden className="size-3.5" strokeWidth={3} /> : <Icon aria-hidden className="size-3.5" />}
                </span>
                <span className={cn('whitespace-nowrap', state === 'current' ? 'hidden sm:inline' : 'hidden md:inline')}>
                  {index + 1}. {meta.short}
                </span>
                <span className="sr-only">{state === 'done' ? ' (done)' : state === 'current' ? ' (now)' : ''}</span>
              </span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
