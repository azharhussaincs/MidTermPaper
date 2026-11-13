import { ExternalLink, LifeBuoy, Phone } from 'lucide-react'
import type { Ref } from 'react'

/**
 * Shown whenever the backend sets `requires_urgent_escalation`. Mirrors the backend's fixed crisis
 * message (graph/prompts.py CRISIS_RESOURCES): location-neutral help first, because we do not know
 * which country the person is in; country numbers follow as labelled examples. The scroll margin
 * clears the sticky header (and the mobile progress bar) when the banner is scrolled into view.
 */
export function CrisisBanner({ ref }: { ref?: Ref<HTMLElement> }) {
  return (
    <section ref={ref} role="alert" aria-labelledby="crisis-title" className="scroll-mt-28 border-b border-rose-200 bg-rose-50 lg:scroll-mt-15">
      <div className="mx-auto flex max-w-6xl items-start gap-3 px-4 py-4 sm:px-6">
        <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-rose-600 text-white">
          <LifeBuoy aria-hidden className="size-5" />
        </div>
        <div className="space-y-2 text-rose-950">
          <h2 id="crisis-title" className="font-semibold">
            You deserve support right now. A clinician has been alerted to review this as a priority.
          </h2>
          <p className="text-sm">If you might act on these thoughts or are not safe, please reach out now:</p>
          <ul className="flex flex-wrap gap-2 text-sm font-medium">
            <li className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 ring-1 ring-rose-200">
              <Phone aria-hidden className="size-3.5" />
              In immediate danger: call your local emergency number
            </li>
            <li>
              <a
                className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 ring-1 ring-rose-200 hover:bg-rose-100"
                href="https://findahelpline.com"
                target="_blank"
                rel="noreferrer"
              >
                Find a crisis line in your country: findahelpline.com
                <ExternalLink aria-hidden className="size-3.5" />
              </a>
            </li>
          </ul>
          <p className="text-[13px] text-rose-900">
            Examples: <a className="underline" href="tel:988">988</a> in the US (call or text) · Samaritans{' '}
            <a className="underline" href="tel:116123">116 123</a> in the UK and Ireland ·{' '}
            <a className="underline" href="tel:112">112</a> for emergencies across the EU
          </p>
        </div>
      </div>
    </section>
  )
}
