import {
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  Cloud,
  Cpu,
  HeartHandshake,
  Loader2,
  RefreshCw,
  ServerCrash,
  Sparkles,
  Stethoscope,
  X,
  XCircle,
} from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { api, ApiError, errorMessage } from '../api/client'
import { usePolling } from '../hooks/usePolling'
import { buttonClass, cn } from '../lib/styles'
import type { ProviderName, SystemStatus } from '../types/api'
import { ErrorNotice } from './ui'

export type Workspace = 'home' | 'patient' | 'clinician'

interface TopBarProps {
  workspace: Workspace
  onWorkspaceChange: (workspace: Workspace) => void
  awaitingReviewCount: number
}

export function TopBar({ workspace, onWorkspaceChange, awaitingReviewCount }: TopBarProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-line/80 bg-canvas/95 backdrop-blur-sm">
      <div className="flex h-15 items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={() => onWorkspaceChange('home')}
          aria-current={workspace === 'home' ? 'page' : undefined}
          className="flex min-w-0 items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand"
          title="About MindBridge"
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand text-white">
            <HeartHandshake aria-hidden className="size-[18px]" />
          </span>
          <span className="hidden font-display text-[19px] font-semibold tracking-tight text-ink sm:inline">MindBridge</span>
          <span className="sr-only sm:hidden">MindBridge home</span>
        </button>

        {/* The product's three stages, in order. Stage 2 runs automatically and is not a place to go. */}
        <nav aria-label="MindBridge stages" className="mx-auto">
          <ol className="flex items-center gap-1 sm:gap-2">
            <li>
              <StageLink active={workspace === 'patient'} onClick={() => onWorkspaceChange('patient')} n={1} icon={<ClipboardList aria-hidden className="size-4" />}>
                <span className="hidden md:inline">Patient check-in</span>
                <span className="md:hidden">Check-in</span>
              </StageLink>
            </li>
            <StageArrow />
            <li
              className="hidden items-center gap-1.5 px-1 text-[13px] text-muted sm:flex"
              title="Runs automatically: answers are organised, checked for gaps and contradictions, and screened for safety concerns"
            >
              <Sparkles aria-hidden className="size-4" />
              <span className="hidden lg:inline">AI screening</span>
            </li>
            <StageArrow className="hidden sm:block" />
            <li>
              <StageLink active={workspace === 'clinician'} onClick={() => onWorkspaceChange('clinician')} n={3} icon={<Stethoscope aria-hidden className="size-4" />}>
                <span className="hidden md:inline">Clinician review</span>
                <span className="md:hidden">Review</span>
                {awaitingReviewCount > 0 && <span className="sr-only">{'\u00a0·\u00a0'}</span>}
                {awaitingReviewCount > 0 && (
                  <span
                    title={`${awaitingReviewCount} waiting for review`}
                    className="grid min-w-5 place-items-center rounded-full bg-brand px-1.5 text-[11px] font-semibold leading-5 text-white tabular-nums"
                  >
                    {awaitingReviewCount}
                    <span className="sr-only">{'\u00a0waiting for review'}</span>
                  </span>
                )}
              </StageLink>
            </li>
          </ol>
        </nav>

        {/* Model settings are a staff concern: shown only in the clinician workspace. */}
        <div className="flex w-8 shrink-0 justify-end sm:w-auto">{workspace === 'clinician' && <EngineControl />}</div>
      </div>
    </header>
  )
}

function StageArrow({ className }: { className?: string }) {
  return <ChevronRight aria-hidden className={cn('size-4 shrink-0 text-slate-300', className)} />
}

interface StageLinkProps {
  active: boolean
  onClick: () => void
  n: number
  icon: ReactNode
  children: ReactNode
}

function StageLink({ active, onClick, n, icon, children }: StageLinkProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'inline-flex h-9 items-center gap-2 rounded-full px-3 text-[13px] font-medium transition-colors sm:px-3.5',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        active ? 'bg-white font-semibold text-ink shadow-card ring-1 ring-line/70' : 'text-muted hover:bg-white/60 hover:text-ink',
      )}
    >
      {/* Non-breaking spaces: hidden text keeps its spacing when read aloud or copied. */}
      <span className="sr-only">{`Step ${n}:\u00a0`}</span>
      {icon}
      {children}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Hybrid LLM engine pill + configuration panel
// ---------------------------------------------------------------------------

const PROVIDERS: { value: ProviderName; label: string; hint: string }[] = [
  { value: 'auto', label: 'Automatic', hint: 'Uses the on-device model when ready, otherwise the cloud model.' },
  { value: 'local', label: 'On this device (Ollama)', hint: 'Private: conversations stay on this computer.' },
  { value: 'gemini', label: 'Cloud (Google Gemini)', hint: 'Needs a cloud key on the server.' },
]

interface Pill {
  label: string
  dot: string
  icon: ReactNode
}

function enginePill(status: SystemStatus | null, error: unknown): Pill {
  const spin = <Loader2 aria-hidden className="size-3.5 animate-spin motion-reduce:animate-none" />
  if (!status) {
    return error
      ? { label: 'Assistant offline', dot: 'bg-rose-500', icon: <ServerCrash aria-hidden className="size-3.5" /> }
      : { label: 'Connecting…', dot: 'bg-slate-300', icon: spin }
  }
  const { llm } = status
  if (llm.local_setup === 'in_progress' && llm.active_provider !== 'local') {
    return { label: 'Preparing assistant', dot: 'bg-amber-500', icon: spin }
  }
  if (llm.active_provider === 'local') {
    return { label: 'Assistant ready · on device', dot: 'bg-emerald-500', icon: <Cpu aria-hidden className="size-3.5" /> }
  }
  if (llm.active_provider === 'gemini') {
    return { label: 'Assistant ready', dot: 'bg-emerald-500', icon: <Cloud aria-hidden className="size-3.5" /> }
  }
  return { label: 'Assistant unavailable', dot: 'bg-rose-500', icon: <XCircle aria-hidden className="size-3.5" /> }
}

function EngineControl() {
  const { data: status, error: pollError, refresh } = usePolling(api.system.status, 15_000)
  const panelId = useId()
  const titleId = useId()
  const modelHintId = useId()
  const panelRef = useRef<HTMLDialogElement>(null)
  const [provider, setProvider] = useState<ProviderName>('auto')
  const [localModel, setLocalModel] = useState('')
  const [busy, setBusy] = useState<'apply' | 'recheck' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const pill = enginePill(status, pollError)

  // Reset the form from live status each time the panel opens.
  useEffect(() => {
    const panel = panelRef.current
    if (!panel) return
    const onToggle = (event: Event) => {
      if ((event as ToggleEvent).newState !== 'open') return
      setError(null)
      setSaved(false)
      void refresh().then((fresh) => {
        if (!fresh) return
        setProvider(fresh.llm.configured_provider)
        setLocalModel(fresh.llm.local_model)
      })
    }
    panel.addEventListener('toggle', onToggle)
    return () => panel.removeEventListener('toggle', onToggle)
  }, [refresh])

  async function configure(kind: 'apply' | 'recheck', body: Parameters<typeof api.system.configureLLM>[0]) {
    setBusy(kind)
    setError(null)
    setSaved(false)
    try {
      await api.system.configureLLM(body)
      await refresh()
      setSaved(true)
    } catch (err) {
      setError(
        err instanceof ApiError && err.fieldErrors.length ? err.fieldErrors.map((e) => e.message).join(' ') : errorMessage(err),
      )
    } finally {
      setBusy(null)
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const model = localModel.trim()
    void configure('apply', { provider, local_model: model && model !== status?.llm.local_model ? model : undefined })
  }

  const llm = status?.llm

  return (
    <>
      <button
        type="button"
        popoverTarget={panelId}
        className={cn(
          'inline-flex h-8 max-w-[15rem] items-center gap-2 rounded-full px-2.5 text-[13px] font-medium text-muted hover:bg-slate-100 hover:text-ink',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        )}
      >
        <span aria-hidden className={cn('size-2 shrink-0 rounded-full', pill.dot)} />
        <span className="hidden text-muted sm:inline">{pill.icon}</span>
        <span className="hidden truncate sm:inline">{pill.label}</span>
        <span className="sr-only sm:hidden">{pill.label}</span>
        <span className="sr-only">— assistant settings</span>
      </button>

      {/* Non-modal panel: the page stays usable; light-dismiss via popover="auto". */}
      <dialog
        ref={panelRef}
        id={panelId}
        popover="auto"
        aria-labelledby={titleId}
        className="fixed inset-auto top-[4.5rem] right-4 m-0 w-[min(24rem,calc(100vw-2rem))] rounded-2xl border border-line bg-card p-0 text-ink shadow-float"
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 id={titleId} className="text-sm font-semibold text-ink">
            AI assistant settings
          </h2>
          <button
            type="button"
            popoverTarget={panelId}
            popoverTargetAction="hide"
            className={buttonClass('ghost', 'sm')}
            aria-label="Close assistant settings"
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          {llm ? (
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1.5 rounded-xl bg-slate-50 p-3 text-xs">
              <StatusItem ok={llm.ollama_installed} label="On-device engine installed" />
              <StatusItem ok={llm.ollama_running} label="On-device engine running" />
              <StatusItem ok={llm.local_model_available} label={`Model ${llm.local_model}`} />
              <StatusItem ok={llm.gemini_configured} label="Cloud key set" />
              <StatusItem ok={status.tracing.enabled} label="Activity tracing" />
              <li className="text-slate-600">
                On-device setup: <span className="font-medium text-ink">{llm.local_setup.replace('_', ' ')}</span>
              </li>
            </ul>
          ) : (
            <p className="text-sm text-muted">{pollError ? errorMessage(pollError) : 'Loading status…'}</p>
          )}
          {llm?.local_setup_error && (
            <details className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
              <summary className="cursor-pointer font-medium">On-device setup failed</summary>
              <p className="mt-1 max-h-32 overflow-y-auto break-words whitespace-pre-wrap">{llm.local_setup_error}</p>
            </details>
          )}

          <form onSubmit={onSubmit} className="space-y-3">
            <fieldset className="space-y-1.5">
              <legend className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Provider</legend>
              {PROVIDERS.map((option) => {
                const disabled = option.value === 'gemini' && llm ? !llm.gemini_configured : false
                return (
                  <label
                    key={option.value}
                    className={cn(
                      'flex cursor-pointer items-start gap-2.5 rounded-xl border px-3 py-2',
                      provider === option.value ? 'border-teal-300 bg-teal-50/60' : 'border-line hover:bg-slate-50',
                      disabled && 'cursor-not-allowed opacity-60',
                    )}
                  >
                    <input
                      type="radio"
                      name="provider"
                      value={option.value}
                      checked={provider === option.value}
                      disabled={disabled}
                      onChange={() => setProvider(option.value)}
                      className="mt-0.5 accent-teal-600"
                    />
                    <span className="text-sm">
                      <span className="font-medium text-ink">{option.label}</span>
                      <span className="block text-xs text-muted">
                        {disabled ? 'Not available: no cloud key is set on the server.' : option.hint}
                      </span>
                    </span>
                  </label>
                )
              })}
            </fieldset>

            <div className="space-y-1">
              <label htmlFor={`${panelId}-model`} className="text-xs font-semibold uppercase tracking-wider text-muted">
                On-device model
              </label>
              <input
                id={`${panelId}-model`}
                value={localModel}
                onChange={(e) => setLocalModel(e.target.value)}
                list={`${panelId}-models`}
                pattern="[\w.\-:\/]+"
                maxLength={100}
                aria-describedby={modelHintId}
                className="h-10 w-full rounded-xl border border-line px-3 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-teal-100 user-invalid:border-rose-400"
              />
              <datalist id={`${panelId}-models`}>
                <option value="qwen2.5:7b" />
                <option value="llama3.2" />
                <option value="llama3.1:8b" />
              </datalist>
              <p id={modelHintId} className="text-xs text-muted">
                Missing models download automatically.
              </p>
            </div>

            {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}
            <p role="status" className="text-xs text-emerald-700">
              {saved ? 'Settings saved.' : ''}
            </p>

            <div className="flex flex-wrap justify-between gap-2">
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void configure('recheck', { ensure_local: true })}
                className={buttonClass('secondary', 'sm')}
              >
                <RefreshCw aria-hidden className={cn('size-3.5', busy === 'recheck' && 'animate-spin motion-reduce:animate-none')} />
                Check on-device engine
              </button>
              <button type="submit" disabled={busy !== null} className={buttonClass('primary', 'sm')}>
                {busy === 'apply' && <Loader2 aria-hidden className="size-3.5 animate-spin motion-reduce:animate-none" />}
                Apply
              </button>
            </div>
          </form>
        </div>
      </dialog>
    </>
  )
}

function StatusItem({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-1.5 text-slate-700">
      {ok ? <CheckCircle2 aria-hidden className="size-3.5 text-emerald-600" /> : <XCircle aria-hidden className="size-3.5 text-slate-400" />}
      <span>
        {label}
        <span className="sr-only">: {ok ? 'yes' : 'no'}</span>
      </span>
    </li>
  )
}
