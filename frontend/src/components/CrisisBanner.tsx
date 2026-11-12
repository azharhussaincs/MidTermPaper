import { LifeBuoy, Phone } from 'lucide-react'

/** Shown whenever the backend sets `requires_urgent_escalation`. Text mirrors the backend's fixed crisis message. */
export function CrisisBanner() {
  return (
    <section role="alert" aria-labelledby="crisis-title" className="border-b border-rose-200 bg-rose-50">
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
            <li>
              <a className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 ring-1 ring-rose-200 hover:bg-rose-100" href="tel:988">
                <Phone aria-hidden className="size-3.5" />
                Call or text 988 <span className="font-normal text-rose-800">(US)</span>
              </a>
            </li>
            <li>
              <a className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 ring-1 ring-rose-200 hover:bg-rose-100" href="tel:116123">
                <Phone aria-hidden className="size-3.5" />
                Samaritans 116 123 <span className="font-normal text-rose-800">(UK &amp; IE)</span>
              </a>
            </li>
            <li className="inline-flex items-center rounded-full bg-white px-3 py-1 ring-1 ring-rose-200">
              Emergency:&nbsp;<a className="underline" href="tel:911">911</a>&nbsp;·&nbsp;
              <a className="underline" href="tel:999">999</a>&nbsp;·&nbsp;<a className="underline" href="tel:112">112</a>
            </li>
            <li>
              <a
                className="inline-flex items-center rounded-full bg-white px-3 py-1 ring-1 ring-rose-200 hover:bg-rose-100"
                href="https://findahelpline.com"
                target="_blank"
                rel="noreferrer"
              >
                findahelpline.com
              </a>
            </li>
          </ul>
        </div>
      </div>
    </section>
  )
}
