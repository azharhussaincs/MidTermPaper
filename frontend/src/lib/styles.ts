import type { RiskLevel } from '../types/api'

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ')
}

const BUTTON_VARIANTS = {
  primary: 'bg-brand text-white shadow-card hover:bg-brand-strong disabled:bg-brand/50',
  accent: 'bg-accent text-white shadow-card hover:bg-indigo-700 disabled:bg-accent/50',
  secondary: 'bg-white text-slate-700 border border-line shadow-card hover:bg-slate-50 disabled:text-slate-400',
  danger: 'bg-white text-rose-700 border border-rose-200 shadow-card hover:bg-rose-50 disabled:text-rose-300',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-ink disabled:text-slate-400',
} as const

export type ButtonVariant = keyof typeof BUTTON_VARIANTS

export function buttonClass(variant: ButtonVariant = 'secondary', size: 'sm' | 'md' = 'md'): string {
  return cn(
    'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed',
    size === 'sm' ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm',
    BUTTON_VARIANTS[variant],
  )
}

export const CARD = 'rounded-2xl border border-line bg-card shadow-card'

export const RISK_STYLES: Record<RiskLevel, string> = {
  critical: 'bg-rose-600 text-white ring-rose-600',
  high: 'bg-rose-50 text-rose-700 ring-rose-200',
  elevated: 'bg-amber-50 text-amber-800 ring-amber-200',
  none: 'bg-slate-50 text-slate-600 ring-slate-200',
}
