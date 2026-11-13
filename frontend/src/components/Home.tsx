import { ArrowRight, MessageCircle, ShieldCheck, Sparkles, Stethoscope } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../lib/styles'

interface HomeProps {
  awaitingReviewCount: number
  onStartCheckIn: () => void
  onOpenReview: () => void
}

/** Front door: what MindBridge is, how the three stages connect, and where each role goes next. */
export function Home({ awaitingReviewCount, onStartCheckIn, onOpenReview }: HomeProps) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-5xl flex-col px-5 pt-12 pb-16 sm:px-8 lg:pt-16">
        <div className="order-1 max-w-3xl">
          <p className="text-[13px] font-medium text-brand-strong">Mental health intake · screening support</p>
          <h1 className="mt-3 font-display text-[2rem] leading-[1.15] font-semibold tracking-tight text-balance text-ink sm:text-[2.6rem]">
            A guided check-in that prepares a person&apos;s own words for clinician review
          </h1>
          <p className="mt-4 text-[17px] leading-relaxed text-pretty text-muted">
            Before a first appointment, a person talks through how they have been. MindBridge organises what they share, points out what is
            missing or contradictory, and flags safety concerns, so a qualified clinician can review it quickly. It never diagnoses or
            recommends treatment.
          </p>
        </div>

        {/* The three stages, in order. Stage 2 is automatic and has no screen of its own. */}
        <ol className="order-3 mt-10 grid gap-px overflow-hidden rounded-3xl bg-line/70 ring-1 ring-line/70 md:order-2 md:mt-12 md:grid-cols-3">
          <Stage
            n={1}
            icon={<MessageCircle aria-hidden className="size-5" />}
            title="Patient check-in"
            who="For the person seeking support"
            text="A private, guided conversation about mood, stress, sleep, anxiety, daily life and goals. Pause anytime and come back later."
          />
          <Stage
            n={2}
            icon={<Sparkles aria-hidden className="size-5" />}
            title="AI screening"
            who="Happens automatically"
            text="Answers are sorted into six topics, checked for gaps and contradictions, and screened for risk. Urgent disclosures are escalated straight away."
          />
          <Stage
            n={3}
            icon={<Stethoscope aria-hidden className="size-5" />}
            title="Clinician review"
            who="For a qualified clinician"
            text="The clinician reads the prepared summary and flagged items, then approves it or requests a follow-up. Nothing is final without them."
          />
        </ol>

        <div className="order-2 mt-8 grid gap-3 md:order-3 md:mt-10 md:gap-4 md:grid-cols-2">
          <EntryButton
            onClick={onStartCheckIn}
            primary
            title="Start a check-in"
            text="About 10 minutes. No account or real name needed."
            icon={<MessageCircle aria-hidden className="size-5" />}
          />
          <EntryButton
            onClick={onOpenReview}
            title="Open the review workspace"
            text={
              awaitingReviewCount > 0
                ? `${awaitingReviewCount} check-in${awaitingReviewCount === 1 ? '' : 's'} waiting for review`
                : 'No check-ins waiting right now'
            }
            icon={<Stethoscope aria-hidden className="size-5" />}
          />
        </div>

        <p className="order-4 mt-10 flex items-start gap-2.5 text-[13px] leading-relaxed text-muted">
          <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-brand" />
          <span>
            Screening support only: not a diagnosis or a treatment recommendation. If you are in danger right now, call your local emergency
            number.
          </span>
        </p>
      </div>
    </div>
  )
}

function Stage({ n, icon, title, who, text }: { n: number; icon: ReactNode; title: string; who: string; text: string }) {
  return (
    <li className="flex flex-col gap-3 bg-white p-6 sm:p-7">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-xl bg-brand-soft text-brand-strong">{icon}</span>
        <span className="text-xs font-semibold text-muted tabular-nums">Step {n}</span>
      </div>
      <div>
        <h2 className="font-display text-xl font-semibold text-ink">{title}</h2>
        <p className="mt-0.5 text-[13px] font-medium text-brand-strong">{who}</p>
      </div>
      <p className="text-sm leading-relaxed text-muted">{text}</p>
    </li>
  )
}

interface EntryButtonProps {
  onClick: () => void
  title: string
  text: string
  icon: ReactNode
  primary?: boolean
}

function EntryButton({ onClick, title, text, icon, primary = false }: EntryButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'group flex items-center gap-4 rounded-2xl p-5 text-left transition-colors sm:p-6',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        primary ? 'bg-brand text-white hover:bg-brand-strong' : 'bg-white text-ink shadow-card ring-1 ring-line/70 hover:ring-slate-300',
      )}
    >
      <span className={cn('grid size-11 shrink-0 place-items-center rounded-xl', primary ? 'bg-white/15' : 'bg-brand-soft text-brand-strong')}>
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-lg font-semibold">{title}</span>
        <span className={cn('block text-sm', primary ? 'text-white/80' : 'text-muted')}>{text}</span>
      </span>
      <ArrowRight aria-hidden className="size-5 shrink-0 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" />
    </button>
  )
}
