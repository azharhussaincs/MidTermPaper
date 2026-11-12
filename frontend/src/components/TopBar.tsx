import {
  CheckCircle2,
  ClipboardList,
  Cloud,
  Cpu,
  HeartHandshake,
  Loader2,
  RefreshCw,
  ServerCrash,
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

export type Workspace = 'patient' | 'clinician'

interface TopBarProps {
  workspace: Workspace
  onWorkspaceChange: (workspace: Workspace) => void
  awaitingReviewCount: number
}

export function TopBar({ workspace, onWorkspaceChange, awaitingReviewCount }: TopBarProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-white/90 backdrop-blur-md">
      <div className="mx-auto grid h-16 grid-cols-[auto_1fr_auto] items-center gap-3 px-4 sm:px-6">
        <div className="flex items-center gap-2.5">
          <div className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-teal-500 to-teal-700 text-white shadow-card">
            <HeartHandshake aria-hidden className="size-5" />
          </div>
          <div className="hidden leading-tight sm:block">
            <p className="text-[15px] font-semibold tracking-tight text-ink">MindBridge</p>
            <p className="text-[11px] font-medium text-slate-500">Intake AI · Screening only</p>
          </div>
        </div>

        {/* App navigation (not an ARIA tablist): aria-current marks the active workspace. */}
        <nav aria-label="Workspace" className="justify-self-center">
          <div className="flex rounded-full border border-line bg-slate-100/80 p-1">
            <SegmentButton active={workspace === 'patient'} onClick={() => onWorkspaceChange('patient')}>
              <ClipboardList aria-hidden className="size-4" />
              <span className="hidden md:inline">Patient Assessment</span>
              <span className="md:hidden">Patient</span>
            </SegmentButton>
            <SegmentButton active={workspace === 'clinician'} onClick={() => onWorkspaceChange('clinician')}>
              <Stethoscope aria-hidden className="size-4" />
              <span className="hidden md:inline">Clinician Review Portal</span>
              <span className="md:hidden">Clinician</span>
              {awaitingReviewCount > 0 && (
                <span className="ml-0.5 grid min-w-5 place-items-center rounded-full bg-rose-500 px-1.5 text-[11px] font-bold leading-5 text-white tabular-nums">
                  {awaitingReviewCount}
                  <span className="sr-only"> awaiting review</span>
                </span>
              )}
            </SegmentButton>
          </div>
        </nav>

        <EngineControl />
      </div>
    </header>
  )
}

function SegmentButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm font-medium transition-colors sm:px-4',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        // Selected state uses a surface + shadow + weight change, not colour alone.
        active ? 'bg-white text-ink shadow-card ring-1 ring-line' : 'text-slate-500 hover:text-ink',
      )}
    >
      {children}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Hybrid LLM engine pill + configuration panel
// ---------------------------------------------------------------------------

const PROVIDERS: { value: ProviderName; label: string; hint: string }[] = [
  { value: 'auto', label: 'Auto', hint: 'Local Ollama when ready, otherwise Gemini.' },
  { value: 'local', label: 'Local (Ollama)', hint: 'Private, on-device inference.' },
  { value: 'gemini', label: 'Google Gemini', hint: 'Cloud model; needs GEMINI_API_KEY on the server.' },
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
      ? { label: 'Backend offline', dot: 'bg-rose-500', icon: <ServerCrash aria-hidden className="size-3.5" /> }
      : { label: 'Connecting…', dot: 'bg-slate-300', icon: spin }
  }
  const { llm } = status
  if (llm.local_setup === 'in_progress' && llm.active_provider !== 'local') {
    return { label: 'Setting up local engine', dot: 'bg-amber-500', icon: spin }
  }
  if (llm.active_provider === 'local') {
    return { label: `Local Ollama · ${llm.local_model}`, dot: 'bg-emerald-500', icon: <Cpu aria-hidden className="size-3.5" /> }
  }
  if (llm.active_provider === 'gemini') {
    return { label: 'Gemini Connected', dot: 'bg-emerald-500', icon: <Cloud aria-hidden className="size-3.5" /> }
  }
  return { label: 'No AI engine', dot: 'bg-rose-500', icon: <XCircle aria-hidden className="size-3.5" /> }
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
          'inline-flex h-8 max-w-[15rem] items-center gap-2 rounded-full border border-line bg-white px-3 text-xs font-medium text-slate-700 shadow-card',
          'hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
        )}
      >
        <span aria-hidden className={cn('size-2 shrink-0 rounded-full', pill.dot)} />
        <span className="hidden text-slate-400 sm:inline">{pill.icon}</span>
        <span className="hidden truncate sm:inline">{pill.label}</span>
        <span className="sr-only sm:hidden">{pill.label}</span>
        <span className="sr-only">— engine settings</span>
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
            AI engine
          </h2>
          <button
            type="button"
            popoverTarget={panelId}
            popoverTargetAction="hide"
            className={buttonClass('ghost', 'sm')}
            aria-label="Close engine settings"
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          {llm ? (
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1.5 rounded-xl bg-slate-50 p-3 text-xs">
              <StatusItem ok={llm.ollama_installed} label="Ollama installed" />
              <StatusItem ok={llm.ollama_running} label="Ollama running" />
              <StatusItem ok={llm.local_model_available} label={`Model ${llm.local_model}`} />
              <StatusItem ok={llm.gemini_configured} label="Gemini key set" />
              <StatusItem ok={status.tracing.enabled} label="LangSmith tracing" />
              <li className="text-slate-600">
                Local setup: <span className="font-medium text-ink">{llm.local_setup.replace('_', ' ')}</span>
              </li>
            </ul>
          ) : (
            <p className="text-sm text-slate-500">{pollError ? errorMessage(pollError) : 'Loading status…'}</p>
          )}
          {llm?.local_setup_error && (
            <details className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
              <summary className="cursor-pointer font-medium">Local setup failed</summary>
              <p className="mt-1 max-h-32 overflow-y-auto break-words whitespace-pre-wrap">{llm.local_setup_error}</p>
            </details>
          )}

          <form onSubmit={onSubmit} className="space-y-3">
            <fieldset className="space-y-1.5">
              <legend className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Provider</legend>
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
                      <span className="block text-xs text-slate-500">
                        {disabled ? 'Unavailable: GEMINI_API_KEY is not configured.' : option.hint}
                      </span>
                    </span>
                  </label>
                )
              })}
            </fieldset>

            <div className="space-y-1">
              <label htmlFor={`${panelId}-model`} className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Local model
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
              <p id={modelHintId} className="text-xs text-slate-500">
                Must support tool calling. Missing models are pulled automatically.
              </p>
            </div>

            {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}
            <p role="status" className="text-xs text-emerald-700">
              {saved ? 'Engine configuration updated.' : ''}
            </p>

            <div className="flex flex-wrap justify-between gap-2">
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void configure('recheck', { ensure_local: true })}
                className={buttonClass('secondary', 'sm')}
              >
                <RefreshCw aria-hidden className={cn('size-3.5', busy === 'recheck' && 'animate-spin motion-reduce:animate-none')} />
                Re-check local engine
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
