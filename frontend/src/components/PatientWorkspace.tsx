import { ArrowUp, Check, ClipboardCheck, HeartHandshake, Lock, Menu, PauseCircle, Plus, ShieldCheck, Sparkles, Timer } from 'lucide-react'
import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { api, errorMessage } from '../api/client'
import { usePolling } from '../hooks/usePolling'
import { DOMAIN_META } from '../lib/domains'
import { formatTime } from '../lib/format'
import { detectQuickReplies } from '../lib/quickReplies'
import { buttonClass, CARD, cn } from '../lib/styles'
import type { AssessmentDetail, AssessmentDomain, ChatMessage } from '../types/api'
import { CrisisBanner } from './CrisisBanner'
import { ConfirmationCard } from './patient/ConfirmationCard'
import { DomainStepper } from './patient/DomainStepper'
import { QuickReplies } from './patient/QuickReplies'
import { NewSessionForm, SessionDrawer } from './patient/SessionDrawer'
import { ConfirmDialog, ErrorNotice } from './ui'

const PAUSE_MESSAGE = 'Please pause here and save my progress so I can continue later.'
const LAST_SESSION_KEY = 'mindbridge:last-session'

function readLastSession(): string | null {
  try {
    return localStorage.getItem(LAST_SESSION_KEY)
  } catch {
    return null
  }
}

function rememberSession(id: string): void {
  try {
    localStorage.setItem(LAST_SESSION_KEY, id)
  } catch {
    // Storage unavailable (private mode etc.): sessions can still be resumed from the drawer.
  }
}

interface PatientWorkspaceProps {
  /** Called after anything that can change the clinician queue. */
  onQueueChanged: () => void
}

export function PatientWorkspace({ onQueueChanged }: PatientWorkspaceProps) {
  const listSessions = useCallback((signal: AbortSignal) => api.assessments.list({ limit: 100 }, signal), [])
  const sessions = usePolling(listSessions, 10_000)
  const [selectedId, setSelectedId] = useState<string | null>(readLastSession)
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
      // e.g. a remembered session that no longer exists
      if (!controller.signal.aborted && !fresh) setSelectedId(null)
    })
    return () => controller.abort()
  }, [selectedId, loadDetail])

  function select(id: string) {
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
  if (loading) return <p className="m-auto text-sm text-slate-500">Loading…</p>
  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-4 py-10">
      <div className="space-y-2 text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-teal-500 to-teal-700 text-white shadow-float">
          <HeartHandshake aria-hidden className="size-7" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Intake screening</h1>
        <p className="text-slate-500">Confidential · reviewed by a clinician</p>
      </div>

      <div className={cn(CARD, 'space-y-5 p-5')}>
        <ul className="flex justify-between gap-2 text-xs font-medium text-slate-600">
          <li className="flex items-center gap-1.5" title="About 10 minutes across 6 short topics">
            <Timer aria-hidden className="size-4 text-brand" />
            ~10 min
          </li>
          <li className="flex items-center gap-1.5" title="Pause anytime; your progress is saved">
            <PauseCircle aria-hidden className="size-4 text-brand" />
            Pause anytime
          </li>
          <li className="flex items-center gap-1.5" title="A screening for a clinician to review, never a diagnosis">
            <ShieldCheck aria-hidden className="size-4 text-brand" />
            Not a diagnosis
          </li>
        </ul>
        <NewSessionForm onCreated={onCreated} prominent />
      </div>

      {hasSessions && (
        <button type="button" onClick={onOpenSessions} aria-haspopup="dialog" className={cn(buttonClass('ghost'), 'mx-auto')}>
          <Menu aria-hidden className="size-4" />
          Resume a session
        </button>
      )}
    </div>
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

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    endRef.current?.scrollIntoView({ block: 'end', behavior: reduce ? 'auto' : 'smooth' })
  }, [visible.length, pending, locked])

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

  return (
    <>
      {/* Top strip: sessions · new · 6-step bar · progress */}
      <div className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5 sm:px-6">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={onOpenSessions}
              aria-haspopup="dialog"
              title={`Current: ${detail.patient_alias ?? 'anonymous'} · switch or resume`}
              className={buttonClass('secondary', 'sm')}
            >
              <Menu aria-hidden className="size-4" />
              Sessions
            </button>
            <button type="button" onClick={onNewSession} disabled={creating} title="Start a new assessment" className={buttonClass('primary', 'sm')}>
              <Plus aria-hidden className="size-4" />
              New
            </button>
          </div>

          <div className="order-last flex w-full justify-center-safe overflow-x-auto sm:order-none sm:w-auto sm:flex-1">
            <DomainStepper progress={detail.domain_completion_map} />
          </div>

          <span
            className={cn(
              'ml-auto rounded-full px-2.5 py-1 text-xs font-semibold tabular-nums sm:ml-0',
              percent >= 100 ? 'bg-emerald-50 text-emerald-700' : 'bg-teal-50 text-brand-strong',
            )}
            title="Screening progress"
          >
            {percent}%
          </span>
        </div>
      </div>

      {detail.requires_urgent_escalation && <CrisisBanner />}

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-4 py-6 sm:px-6">
          {error && (
            <div className="mb-4">
              <ErrorNotice message={error} onDismiss={() => onError(null)} />
            </div>
          )}
          <ol role="log" aria-live="polite" aria-label="Conversation" className="space-y-4">
            {visible.map((message, index) => (
              <MessageItem key={message.id ?? index} message={message} />
            ))}
            {pending && (
              <MessageItem message={{ id: null, created_at: null, role: 'user', content: pending, tool_calls: null, name: null }} />
            )}
            {busy === 'send' && <TypingIndicator />}
            {busy === 'finalize' && <TypingIndicator label="Submitting…" />}
            <li ref={endRef} aria-hidden className="h-px" />
          </ol>

          {locked && (
            <div className="mt-6">
              <ConfirmationCard detail={detail} />
            </div>
          )}
        </div>
      </div>

      {locked ? (
        <p className="flex items-center justify-center gap-2 border-t border-line bg-white px-4 py-3 text-sm text-slate-500">
          <Lock aria-hidden className="size-4" />
          {detail.status === 'reviewed' ? 'Complete' : 'With a clinician'}
        </p>
      ) : (
        <div className="border-t border-line bg-white/95 backdrop-blur">
          <form
            ref={formRef}
            onSubmit={(e) => {
              e.preventDefault()
              void send(draft, { fromDraft: true })
            }}
            className="mx-auto max-w-2xl space-y-2.5 px-4 py-3 sm:px-6"
          >
            {/* Action bar: one-tap answers on the left, session actions on the right */}
            <div className="flex items-start gap-2">
              {quickReplies ? (
                <QuickReplies set={quickReplies} disabled={busy !== null} onPick={pickQuickReply} />
              ) : (
                <p className="min-w-0 flex-1 truncate pt-1.5 text-xs text-slate-400">
                  {detail.status === 'interrupted' ? 'Paused · answers saved' : 'Type your answer below'}
                </p>
              )}
              <div className="flex shrink-0 gap-1.5">
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void send(PAUSE_MESSAGE, { fromDraft: false })}
                  className={buttonClass('ghost', 'sm')}
                  title="Pause and save your progress"
                >
                  <PauseCircle aria-hidden className="size-4" />
                  <span className="hidden sm:inline">Pause</span>
                  <span className="sr-only sm:hidden">Pause</span>
                </button>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => setConfirmOpen(true)}
                  className={buttonClass('ghost', 'sm')}
                  title="Send what you've answered so far to a clinician"
                >
                  <ClipboardCheck aria-hidden className="size-4" />
                  <span className="hidden sm:inline">Submit now</span>
                  <span className="sr-only sm:hidden">Submit now</span>
                </button>
              </div>
            </div>

            <div className="flex items-end gap-2 rounded-2xl border border-line bg-white p-1.5 shadow-card focus-within:border-teal-300 focus-within:ring-4 focus-within:ring-teal-50">
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
                placeholder="Type your answer…"
                title="Enter to send · Shift+Enter for a new line"
                disabled={busy !== null}
                className="max-h-40 min-h-10 flex-1 resize-none border-0 bg-transparent px-2.5 py-2 text-[15px] [field-sizing:content] placeholder:text-slate-400 focus:outline-none disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={busy !== null || !draft.trim()}
                className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand text-white shadow-card transition-colors hover:bg-brand-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:bg-slate-200 disabled:text-slate-400"
                aria-label="Send"
              >
                <ArrowUp aria-hidden className="size-5" />
              </button>
            </div>
          </form>
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title={`Submit now at ${percent}%?`}
        confirmLabel="Submit"
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => void finalize()}
      >
        <p>A clinician reviews what you’ve shared so far. You can’t add answers afterwards.</p>
      </ConfirmDialog>
    </>
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
    <span role="img" aria-label="Assistant" className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-teal-50 text-brand ring-1 ring-teal-100">
      <Sparkles aria-hidden className="size-4" />
    </span>
  )
}

function MessageItem({ message }: { message: ChatMessage }) {
  if (message.role === 'tool') {
    const domain = savedDomain(message)
    return (
      <li className="flex justify-center">
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
          <Check aria-hidden className="size-3" strokeWidth={3} />
          Saved: {domain ? DOMAIN_META[domain].short : 'answer'}
        </span>
      </li>
    )
  }
  const isUser = message.role === 'user'
  const time = message.created_at ? formatTime(message.created_at) : undefined
  return (
    <li className={cn('flex gap-2.5', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && <BotAvatar />}
      <div
        title={time}
        className={cn(
          'max-w-[82%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed',
          isUser ? 'rounded-br-md bg-brand text-white shadow-card' : 'rounded-tl-md border border-line bg-white text-ink shadow-card',
        )}
      >
        {message.content}
        {time && (
          <time
            dateTime={message.created_at ?? undefined}
            className={cn('mt-1 block text-right text-[10px]', isUser ? 'text-teal-100' : 'text-slate-400')}
          >
            {time}
          </time>
        )}
      </div>
    </li>
  )
}

function TypingIndicator({ label = 'Typing…' }: { label?: string }) {
  return (
    <li className="flex gap-2.5">
      <BotAvatar />
      <div role="status" className="inline-flex items-center gap-2 rounded-2xl rounded-tl-md border border-line bg-white px-4 py-3 text-xs text-slate-500 shadow-card">
        <span aria-hidden className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <span key={i} className="typing-dot size-1.5 rounded-full bg-brand" style={{ animationDelay: `${i * 0.2}s` }} />
          ))}
        </span>
        <span className="sr-only">{label}</span>
      </div>
    </li>
  )
}
