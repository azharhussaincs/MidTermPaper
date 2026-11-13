import { ArrowUp, Check, ChevronDown, ClipboardCheck, History, Lock, Menu, MessageCircle, PauseCircle, Plus, ShieldCheck, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { api, errorMessage } from '../api/client'
import { usePolling } from '../hooks/usePolling'
import { DOMAIN_META } from '../lib/domains'
import { formatTime } from '../lib/format'
import { summarizeCheckIn } from '../lib/outcome'
import { detectQuickReplies } from '../lib/quickReplies'
import { buttonClass, cn } from '../lib/styles'
import { ASSESSMENT_DOMAINS, type AssessmentDetail, type AssessmentDomain, type ChatMessage } from '../types/api'
import { CrisisBanner } from './CrisisBanner'
import { ConfirmationCard } from './patient/ConfirmationCard'
import { DomainStepper } from './patient/DomainStepper'
import { QuickReplies } from './patient/QuickReplies'
import { ProgressRail } from './patient/ProgressRail'
import { NewSessionForm, SessionDrawer } from './patient/SessionDrawer'
import { ConfirmDialog, ErrorNotice, LoadingState } from './ui'

const LOCKED_FOOTER = {
  safety_pause: 'Paused for your safety · a clinician will review this first',
  sent_partial: 'Sent before finishing · a clinician will review what you shared',
  sent_complete: 'Sent · a clinician will review it',
  reviewed: 'This check-in has been reviewed',
} as const

const PAUSE_MESSAGE = 'Please pause here and save my progress so I can continue later.'
const LAST_SESSION_KEY = 'mindbridge:last-session'
const TAB_SESSION_KEY = 'mindbridge:tab-session'

/**
 * Which check-in to open on load. This tab's own session (sessionStorage) survives a refresh, so a
 * safety screen never disappears while the patient is still here. Across visits (localStorage) only an
 * unfinished check-in is resumed; a submitted or safety-paused one stays in "Saved check-ins" instead
 * of reopening every time.
 */
function readLastSession(): { id: string; thisTab: boolean } | null {
  try {
    const tab = sessionStorage.getItem(TAB_SESSION_KEY)
    if (tab) return { id: tab, thisTab: true }
    const last = localStorage.getItem(LAST_SESSION_KEY)
    return last ? { id: last, thisTab: false } : null
  } catch {
    return null
  }
}

function rememberSession(id: string): void {
  try {
    sessionStorage.setItem(TAB_SESSION_KEY, id)
    localStorage.setItem(LAST_SESSION_KEY, id)
  } catch {
    // Storage unavailable (private mode etc.): sessions can still be resumed from the drawer.
  }
}

/** Stop resuming a finished check-in on later visits (this tab keeps it until it is closed). */
function forgetAcrossVisits(id: string): void {
  try {
    if (localStorage.getItem(LAST_SESSION_KEY) === id) localStorage.removeItem(LAST_SESSION_KEY)
  } catch {
    // Nothing to forget.
  }
}

function isClosed(detail: AssessmentDetail): boolean {
  return detail.status === 'awaiting_clinician_review' || detail.status === 'reviewed' || detail.pending_review !== null
}

interface PatientWorkspaceProps {
  /** Called after anything that can change the clinician queue. */
  onQueueChanged: () => void
}

export function PatientWorkspace({ onQueueChanged }: PatientWorkspaceProps) {
  const listSessions = useCallback((signal: AbortSignal) => api.assessments.list({ limit: 100 }, signal), [])
  const sessions = usePolling(listSessions, 10_000)
  const [initial] = useState(readLastSession)
  const [selectedId, setSelectedId] = useState<string | null>(initial?.id ?? null)
  // Set only when the check-in was reopened from an earlier visit rather than this tab.
  const fromEarlierVisit = useRef(initial && !initial.thisTab ? initial.id : null)
  const [loadedDetail, setDetail] = useState<AssessmentDetail | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Derived: never show the previously selected session's data while the next one loads.
  const detail = loadedDetail?.session_id === selectedId ? loadedDetail : null

  const loadDetail = useCallback(async (id: string, signal?: AbortSignal) => {
    try {
      const fresh = await api.assessments.get(id, signal)
      setDetail(fresh)
      return fresh
    } catch (err) {
      if (signal?.aborted) return null
      setError(errorMessage(err))
      return null
    }
  }, [])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    void loadDetail(selectedId, controller.signal).then((fresh) => {
      if (controller.signal.aborted) return
      // e.g. a remembered session that no longer exists
      if (!fresh) return setSelectedId(null)
      if (fresh.session_id === fromEarlierVisit.current && isClosed(fresh)) {
        fromEarlierVisit.current = null
        forgetAcrossVisits(fresh.session_id)
        setSelectedId(null)
      }
    })
    return () => controller.abort()
  }, [selectedId, loadDetail])

  function select(id: string) {
    fromEarlierVisit.current = null
    rememberSession(id)
    setError(null)
    setSelectedId(id)
  }

  function created(fresh: AssessmentDetail) {
    setDetail(fresh)
    select(fresh.session_id)
    void sessions.refresh()
  }

  /** "+ New" in the top strip: start immediately with a generated anonymous alias. */
  async function startNew() {
    if (creating) return
    setCreating(true)
    setError(null)
    try {
      created(await api.assessments.start({}))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setCreating(false)
    }
  }

  async function afterChange(id: string): Promise<AssessmentDetail | null> {
    const [fresh] = await Promise.all([loadDetail(id), sessions.refresh()])
    if (fresh && isClosed(fresh)) forgetAcrossVisits(id)
    onQueueChanged()
    return fresh
  }

  return (
    <div className="flex h-full min-h-[calc(100dvh-4rem)] flex-col lg:min-h-0">
      {detail ? (
        <ChatPanel
          key={detail.session_id}
          detail={detail}
          creating={creating}
          onOpenSessions={() => setDrawerOpen(true)}
          onNewSession={() => void startNew()}
          onChanged={() => afterChange(detail.session_id)}
          onError={setError}
          error={error}
        />
      ) : (
        <Welcome
          loading={selectedId !== null}
          hasSessions={(sessions.data?.items.length ?? 0) > 0}
          onOpenSessions={() => setDrawerOpen(true)}
          onCreated={created}
        />
      )}

      <SessionDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        sessions={sessions.data?.items ?? []}
        selectedId={selectedId}
        onSelect={select}
        onCreated={created}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Welcome (no session selected)
// ---------------------------------------------------------------------------

interface WelcomeProps {
  loading: boolean
  hasSessions: boolean
  onOpenSessions: () => void
  onCreated: (detail: AssessmentDetail) => void
}

function Welcome({ loading, hasSessions, onOpenSessions, onCreated }: WelcomeProps) {
  if (loading) return <LoadingState label="Loading your check-in…" variant="chat" />
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-5 pt-12 pb-16 sm:px-8 lg:pt-20">
        <div className="space-y-4 text-center">
          <p className="inline-flex items-center gap-1.5 text-[13px] font-medium text-brand-strong">
            <Lock aria-hidden className="size-3.5" />
            Private check-in · about 10 minutes
          </p>
          <h1 className="font-display text-[2rem] leading-[1.15] font-semibold tracking-tight text-balance text-ink sm:text-[2.6rem]">
            How have you been feeling lately?
          </h1>
          <p className="mx-auto max-w-xl text-[17px] leading-relaxed text-pretty text-muted">
            This guided check-in helps your clinician understand how you have been before your appointment. Answer in your own words,
            at your own pace.
          </p>
        </div>

        <div className="mt-10 overflow-hidden rounded-3xl bg-white shadow-raised ring-1 ring-line/70">
          <div className="px-6 pt-7 pb-6 sm:px-9">
            <p className="text-center text-[13px] font-medium text-muted">We&apos;ll gently cover six topics</p>
            <ol className="mt-5 grid grid-cols-3 gap-x-2 gap-y-5 sm:grid-cols-6">
              {ASSESSMENT_DOMAINS.map((domain, index) => {
                const meta = DOMAIN_META[domain]
                const Icon = meta.icon
                return (
                  <li key={domain} className="flex flex-col items-center gap-2 text-center">
                    <span className="grid size-11 place-items-center rounded-2xl bg-brand-soft text-brand-strong">
                      <Icon aria-hidden className="size-5" />
                    </span>
                    <span className="text-[13px] leading-tight font-medium text-ink">
                      <span className="sr-only">{index + 1}. </span>
                      {meta.short}
                    </span>
                  </li>
                )
              })}
            </ol>
          </div>

          <div className="grid gap-8 border-t border-line/70 bg-slate-50/60 px-6 py-7 sm:px-9 md:grid-cols-[1fr_1.1fr] md:gap-10">
            <ul className="space-y-3.5 text-sm text-muted">
              <Reassurance icon={<MessageCircle aria-hidden className="size-4" />}>Skip any question you would rather not answer.</Reassurance>
              <Reassurance icon={<PauseCircle aria-hidden className="size-4" />}>Pause anytime. Your answers are saved.</Reassurance>
              <Reassurance icon={<ShieldCheck aria-hidden className="size-4" />}>A clinician reads it. It is not a diagnosis.</Reassurance>
            </ul>
            <div className="space-y-3">
              <NewSessionForm onCreated={onCreated} prominent />
              <p className="text-[13px] leading-relaxed text-muted">
                <span className="font-medium text-ink">What happens after:</span> your answers are organised and sent to a clinician, who reads
                them before your appointment.
              </p>
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-col items-center gap-4 text-center">
          {hasSessions && (
            <button type="button" onClick={onOpenSessions} aria-haspopup="dialog" className={buttonClass('ghost')}>
              <History aria-hidden className="size-4" />
              Continue a saved check-in
            </button>
          )}
          <p className="text-[13px] text-muted">If you are in danger right now, call your local emergency number.</p>
        </div>
      </div>
    </div>
  )
}

function Reassurance({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <li className="flex items-center gap-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-white text-brand ring-1 ring-line">{icon}</span>
      <span className="text-ink">{children}</span>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

interface ChatPanelProps {
  detail: AssessmentDetail
  error: string | null
  creating: boolean
  onOpenSessions: () => void
  onNewSession: () => void
  /** Reloads the session; resolves with the fresh state. */
  onChanged: () => Promise<AssessmentDetail | null>
  onError: (message: string | null) => void
}

function ChatPanel({ detail, error, creating, onOpenSessions, onNewSession, onChanged, onError }: ChatPanelProps) {
  const inputId = useId()
  const formRef = useRef<HTMLFormElement>(null)
  const endRef = useRef<HTMLLIElement>(null)
  const crisisRef = useRef<HTMLElement>(null)
  const sendingRef = useRef(false)
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const [busy, setBusy] = useState<'send' | 'finalize' | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const locked = detail.status === 'awaiting_clinician_review' || detail.status === 'reviewed' || detail.pending_review !== null
  const visible = detail.messages.filter(isVisibleMessage)
  const last = visible.at(-1)
  const quickReplies = !locked && !pending && last?.role === 'assistant' ? detectQuickReplies(last.content) : null
  const percent = Math.round(detail.completion_pct)

  const urgent = detail.requires_urgent_escalation
  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!urgent) {
      endRef.current?.scrollIntoView({ block: 'end', behavior: reduce ? 'auto' : 'smooth' })
      return
    }
    // Safety pause: bring the latest messages into the conversation pane, then make sure the crisis
    // contacts are on screen. On phones the page itself scrolls, so the second call wins there.
    endRef.current?.scrollIntoView({ block: 'end' })
    crisisRef.current?.scrollIntoView({ block: 'start' })
  }, [visible.length, pending, locked, urgent])

  async function send(text: string, { fromDraft }: { fromDraft: boolean }) {
    const message = text.trim()
    // The ref blocks a second tap that lands before React re-renders with `busy` set.
    if (!message || busy || sendingRef.current) return
    sendingRef.current = true
    setBusy('send')
    setPending(message)
    if (fromDraft) setDraft('')
    onError(null)
    try {
      await api.assessments.sendMessage(detail.session_id, { message })
      await onChanged()
    } catch (err) {
      onError(errorMessage(err))
      // The server may have saved the message before failing (e.g. LLM outage). Only give the
      // text back if it isn't in the history, so a retry can't duplicate it.
      const fresh = await onChanged()
      const lastUser = fresh?.messages.findLast((m) => m.role === 'user')
      if (fromDraft && lastUser?.content !== message) setDraft(message)
    } finally {
      sendingRef.current = false
      setPending(null)
      setBusy(null)
    }
  }

  async function finalize() {
    setBusy('finalize')
    onError(null)
    try {
      await api.assessments.finalize(detail.session_id)
      await onChanged()
    } catch (err) {
      onError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  function pickQuickReply(value: string) {
    // One tap sends. Anything already typed in the box goes along with the chosen answer.
    const typed = draft.trim()
    void send(typed ? `${typed}, ${value}` : value, { fromDraft: typed !== '' })
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      // Don't submit while an IME is composing (keyCode 229 covers Safari's event ordering).
      if (event.nativeEvent.isComposing || event.keyCode === 229) return
      formRef.current?.requestSubmit()
    }
  }

  const lastAssistantIndex = visible.findLastIndex((m) => m.role === 'assistant')
  // One question at a time: the last answer, what was saved, and the current question stay in view;
  // everything before it folds into "Earlier in this check-in".
  const lastAnswerIndex = visible.slice(0, Math.max(lastAssistantIndex, 0)).findLastIndex((m) => m.role === 'user')
  const paused = detail.status === 'interrupted' && !locked
  // While paused, the question to answer next is the one asked before the pause, not the
  // "progress saved" reply (the backend's fixed pause message).
  const resumeIndex =
    paused && visible[lastAssistantIndex]?.content.startsWith('Your progress is saved')
      ? visible.slice(0, lastAssistantIndex).findLastIndex((m) => m.role === 'assistant' && m.content.includes('?'))
      : -1
  const focusStart = lastAssistantIndex < 0 ? 0 : lastAnswerIndex >= 0 ? lastAnswerIndex : lastAssistantIndex
  const earlier = resumeIndex >= 0 ? visible.filter((_, i) => i !== resumeIndex) : visible.slice(0, focusStart)
  const focus = resumeIndex >= 0 ? [visible[resumeIndex]] : visible.slice(focusStart)
  const currentIndex = resumeIndex >= 0 ? resumeIndex : lastAssistantIndex
  const currentTopic = ASSESSMENT_DOMAINS.find((domain) => !detail.domain_completion_map[domain]?.completed)

  return (
    <div className="flex min-h-0 flex-1">
      <ProgressRail
        detail={detail}
        locked={locked}
        busy={busy !== null}
        creating={creating}
        onPause={() => void send(PAUSE_MESSAGE, { fromDraft: false })}
        onSubmit={() => setConfirmOpen(true)}
        onOpenSessions={onOpenSessions}
        onNewSession={onNewSession}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Compact progress for phones and tablets; the rail replaces it on desktop. */}
        <div className="sticky top-15 z-20 border-b border-line/80 bg-canvas/95 backdrop-blur-sm lg:hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 sm:px-6">
            <button type="button" onClick={onOpenSessions} aria-haspopup="dialog" className={buttonClass('ghost', 'sm')} title="Saved check-ins">
              <Menu aria-hidden className="size-4" />
              <span className="sr-only sm:not-sr-only">Sessions</span>
            </button>
            <div className="flex min-w-0 flex-1 justify-center-safe overflow-x-auto">
              <DomainStepper progress={detail.domain_completion_map} />
            </div>
            <span className="text-sm whitespace-nowrap text-ink" title={`${percent}% complete`}>
              {currentTopic && !locked && <span className="mr-1.5 font-medium sm:hidden">{DOMAIN_META[currentTopic].short}</span>}
              <span className="font-semibold tabular-nums">{percent}%</span>
            </span>
            <button type="button" onClick={onNewSession} disabled={creating} className={buttonClass('ghost', 'sm')} title="Start a new check-in">
              <Plus aria-hidden className="size-4" />
              <span className="sr-only sm:not-sr-only">New Session</span>
            </button>
          </div>
          <div aria-hidden className="h-0.5 bg-slate-200/70">
            <div className="h-full bg-brand transition-[width] duration-500 motion-reduce:transition-none" style={{ width: `${percent}%` }} />
          </div>
        </div>

        {urgent && <CrisisBanner ref={crisisRef} />}

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-2xl px-5 pt-8 pb-10 sm:px-8">
            {error && (
              <div className="mb-6">
                <ErrorNotice message={error} onDismiss={() => onError(null)} />
              </div>
            )}
            {paused && (
              <div className="mb-8 flex items-start gap-3.5 rounded-2xl bg-white px-5 py-4 shadow-card ring-1 ring-line/70">
                <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-amber-50 text-amber-700">
                  <PauseCircle aria-hidden className="size-4" />
                </span>
                <div className="min-w-0 flex-1 space-y-2.5 sm:flex sm:items-center sm:justify-between sm:gap-4 sm:space-y-0">
                  <div>
                    <p className="text-[15px] font-semibold text-ink">Paused. Your answers are saved</p>
                    <p className="text-sm text-muted">Pick up with the question below whenever you are ready.</p>
                  </div>
                  <button type="button" onClick={() => document.getElementById(inputId)?.focus()} className={buttonClass('secondary', 'sm')}>
                    Continue
                  </button>
                </div>
              </div>
            )}

            {earlier.length > 0 && (
              <details className="group mb-8 rounded-2xl ring-1 ring-line/70 open:bg-white/60">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm text-muted [&::-webkit-details-marker]:hidden">
                  <span className="flex items-center gap-2">
                    <History aria-hidden className="size-4" />
                    Earlier in this check-in
                    <span className="tabular-nums">· {plural(earlier.filter((m) => m.role === 'user').length, 'reply', 'replies')}</span>
                  </span>
                  <ChevronDown aria-hidden className="size-4 transition-transform group-open:rotate-180 motion-reduce:transition-none" />
                </summary>
                <ol aria-label="Earlier in this check-in" className="space-y-4 border-t border-line/70 px-4 py-4">
                  {earlier.map((message, index) => (
                    <MessageItem key={message.id ?? `e${index}`} message={message} compact />
                  ))}
                </ol>
              </details>
            )}

            <ol role="log" aria-live="polite" aria-label="Conversation" className="space-y-6">
              {focus.map((message, index) => (
                <MessageItem
                  key={message.id ?? `f${index}`}
                  message={message}
                  current={!locked && !pending && (resumeIndex >= 0 ? index === 0 : focusStart + index === currentIndex)}
                />
              ))}
              {pending && (
                <MessageItem message={{ id: null, created_at: null, role: 'user', content: pending, tool_calls: null, name: null }} />
              )}
              {busy === 'send' && <TypingIndicator />}
              {busy === 'finalize' && <TypingIndicator label="Sending…" />}
              <li ref={endRef} aria-hidden className="h-px" />
            </ol>

            {locked && (
              <div className="mt-10">
                <ConfirmationCard detail={detail} />
              </div>
            )}
          </div>
        </div>

        {locked ? (
          <p className="flex items-center justify-center gap-2 border-t border-line/80 px-4 py-3.5 text-sm text-muted">
            <Lock aria-hidden className="size-4" />
            {LOCKED_FOOTER[summarizeCheckIn(detail).outcome]}
          </p>
        ) : (
          <div className="sticky bottom-0 z-20 bg-gradient-to-t from-canvas via-canvas to-canvas/0 pt-2">
            <form
              ref={formRef}
              onSubmit={(e) => {
                e.preventDefault()
                void send(draft, { fromDraft: true })
              }}
              className="mx-auto max-w-2xl space-y-3 px-5 pb-5 sm:px-8"
            >
              {quickReplies && <QuickReplies set={quickReplies} disabled={busy !== null} onPick={pickQuickReply} />}

              <div className="flex items-end gap-2 rounded-2xl bg-white p-2 shadow-raised ring-1 ring-line transition-shadow focus-within:ring-2 focus-within:ring-brand/40">
                <label htmlFor={inputId} className="sr-only">
                  Your answer
                </label>
                <textarea
                  id={inputId}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={onKeyDown}
                  rows={1}
                  maxLength={4000}
                  placeholder={quickReplies ? 'Pick an answer above, or write your own…' : 'Write your answer…'}
                  title="Enter to send · Shift+Enter for a new line"
                  disabled={busy !== null}
                  className="max-h-40 min-h-11 flex-1 resize-none border-0 bg-transparent px-3 py-2.5 text-base [field-sizing:content] placeholder:text-slate-400 focus:outline-none disabled:opacity-60"
                />
                <button
                  type="submit"
                  disabled={busy !== null || !draft.trim()}
                  className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand text-white transition-colors hover:bg-brand-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:bg-slate-100 disabled:text-slate-400"
                  aria-label="Send"
                >
                  <ArrowUp aria-hidden className="size-5" />
                </button>
              </div>

              {/* Session actions on smaller screens; on desktop they live in the progress rail. */}
              <div className="flex items-center justify-between gap-2 lg:hidden">
                <span className="text-xs text-muted">Saved as you go</span>
                <div className="flex gap-1">
                  {!paused && (
                    <button type="button" disabled={busy !== null} onClick={() => void send(PAUSE_MESSAGE, { fromDraft: false })} className={buttonClass('ghost', 'sm')}>
                      <PauseCircle aria-hidden className="size-4" />
                      Pause
                    </button>
                  )}
                  <button type="button" disabled={busy !== null} onClick={() => setConfirmOpen(true)} className={cn(buttonClass('ghost', 'sm'), 'text-brand-strong')}>
                    <ClipboardCheck aria-hidden className="size-4" />
                    Submit Now
                  </button>
                </div>
              </div>
              <p className="hidden text-center text-xs text-muted lg:block">Your answers are saved as you go.</p>
            </form>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title="Send your answers now?"
        confirmLabel="Send to clinician"
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => void finalize()}
      >
        <p>You have answered {percent}% of the check-in. A clinician will review what you have shared so far.</p>
        <p>You won&apos;t be able to add more answers afterwards.</p>
      </ConfirmDialog>
    </div>
  )
}

function isVisibleMessage(message: ChatMessage): boolean {
  if (message.role === 'tool') return message.name === 'store_assessment_response' && savedDomain(message) !== null
  return (message.role === 'user' || message.role === 'assistant') && message.content.trim() !== ''
}

function savedDomain(message: ChatMessage): AssessmentDomain | null {
  try {
    const parsed = JSON.parse(message.content) as { ok?: boolean; domain?: AssessmentDomain }
    return parsed.ok && parsed.domain ? parsed.domain : null
  } catch {
    return null
  }
}

function BotAvatar() {
  return (
    <span aria-hidden className="mt-1 grid size-7 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-strong">
      <Sparkles aria-hidden className="size-3.5" />
    </span>
  )
}

function MessageItem({ message, current = false, compact = false }: { message: ChatMessage; current?: boolean; compact?: boolean }) {
  if (message.role === 'tool') {
    const domain = savedDomain(message)
    return (
      <li className={cn('flex items-center gap-2 text-xs font-medium text-emerald-700', compact ? 'pl-0' : 'pl-10')}>
        <Check aria-hidden className="size-3.5" strokeWidth={3} />
        {domain ? DOMAIN_META[domain].short : 'Answer'} saved
      </li>
    )
  }
  const time = message.created_at ? formatTime(message.created_at) : undefined
  if (compact) {
    const isUser = message.role === 'user'
    return (
      <li className={cn('text-sm leading-relaxed whitespace-pre-wrap', isUser ? 'pl-4 font-medium text-ink' : 'text-muted')} title={time}>
        {isUser && <span className="sr-only">You: </span>}
        {message.content}
      </li>
    )
  }
  if (message.role === 'user') {
    return (
      <li className="flex justify-end pl-12">
        <div title={time} className="max-w-full rounded-2xl rounded-br-md bg-white px-4 py-3 text-[15px] leading-relaxed whitespace-pre-wrap text-ink shadow-card ring-1 ring-line/70">
          {message.content}
        </div>
      </li>
    )
  }
  // Assistant: no bubble. The question reads as the page's main text; the latest one is emphasised,
  // unless it is long (e.g. the safety message), which reads better at body size.
  const emphasise = current && message.content.length <= 260
  return (
    <li className="flex gap-3" aria-current={current ? 'true' : undefined}>
      <BotAvatar />
      <div
        title={time}
        className={cn(
          'min-w-0 flex-1 space-y-3 font-display leading-relaxed text-ink',
          emphasise ? 'text-[20px] sm:text-[21px]' : current ? 'text-[17px]' : 'text-[17px] text-ink/85',
        )}
      >
        <AssistantText text={message.content} />
      </div>
    </li>
  )
}

/** Paragraphs and "- " lists in the assistant's plain text, rendered as such (no markup is interpreted). */
function AssistantText({ text }: { text: string }) {
  const blocks = text.split(/\n\s*\n/)
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split('\n').map((l) => l.trim()).filter(Boolean)
        const items = lines.filter((l) => l.startsWith('- '))
        if (items.length > 0 && items.length === lines.length - (lines[0].startsWith('- ') ? 0 : 1)) {
          const lead = lines[0].startsWith('- ') ? null : lines[0]
          return (
            <div key={i} className="space-y-1.5">
              {lead && <p>{lead}</p>}
              <ul className="list-disc space-y-1 pl-5 font-sans text-[15px] leading-relaxed marker:text-slate-400">
                {items.map((item) => (
                  <li key={item}>{item.slice(2)}</li>
                ))}
              </ul>
            </div>
          )
        }
        return (
          <p key={i} className="whitespace-pre-wrap">
            {block.trim()}
          </p>
        )
      })}
    </>
  )
}

const SLOW_REPLY_MS = 12_000

function TypingIndicator({ label = 'Typing…' }: { label?: string }) {
  // A slow model call otherwise looks frozen; after a while, say so in plain words.
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), SLOW_REPLY_MS)
    return () => window.clearTimeout(timer)
  }, [])
  return (
    <li className="flex gap-3">
      <BotAvatar />
      <div role="status" className="inline-flex items-center gap-2.5 py-2 text-sm text-muted">
        <span aria-hidden className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <span key={i} className="typing-dot size-1.5 rounded-full bg-brand" style={{ animationDelay: `${i * 0.2}s` }} />
          ))}
        </span>
        {slow ? <span>Taking a little longer than usual. Your answer is saved.</span> : <span className="sr-only">{label}</span>}
      </div>
    </li>
  )
}

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`
}
