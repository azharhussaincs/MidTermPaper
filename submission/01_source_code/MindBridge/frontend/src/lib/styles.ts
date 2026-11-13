import type { RiskLevel } from '../types/api'

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ')
}

const BUTTON_VARIANTS = {
  primary: 'bg-brand text-white shadow-card hover:bg-brand-strong disabled:bg-brand/45',
  accent: 'bg-brand-strong text-white shadow-card hover:bg-teal-900 disabled:bg-brand-strong/45',
  secondary: 'bg-white text-ink border border-line shadow-card hover:border-slate-300 hover:bg-slate-50 disabled:text-slate-400',
  danger: 'bg-white text-rose-700 border border-rose-200 shadow-card hover:bg-rose-50 disabled:text-rose-300',
  ghost: 'text-muted hover:bg-slate-100 hover:text-ink disabled:text-slate-400',
} as const

export type ButtonVariant = keyof typeof BUTTON_VARIANTS

export function buttonClass(variant: ButtonVariant = 'secondary', size: 'sm' | 'md' | 'lg' = 'md'): string {
  return cn(
    'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg font-medium whitespace-nowrap transition-colors',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed',
    size === 'sm' ? 'h-8 px-3 text-[13px]' : size === 'lg' ? 'h-11 px-5 text-[15px]' : 'h-10 px-4 text-sm',
    BUTTON_VARIANTS[variant],
  )
}

export const CARD = 'rounded-2xl border border-line bg-card shadow-card'

/** Small uppercase label above a field or group. */
export const EYEBROW = 'text-xs font-semibold uppercase tracking-wide text-muted'

/** Text inputs and textareas share one look. */
export const INPUT =
  'w-full rounded-lg border border-line bg-white px-3 text-[15px] text-ink placeholder:text-slate-400 transition-colors ' +
  'focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand-soft user-invalid:border-rose-400'

export const RISK_STYLES: Record<RiskLevel, string> = {
  critical: 'bg-rose-600 text-white ring-rose-600',
  high: 'bg-rose-50 text-rose-700 ring-rose-200',
  elevated: 'bg-amber-50 text-amber-800 ring-amber-200',
  none: 'bg-slate-50 text-slate-600 ring-slate-200',
}
