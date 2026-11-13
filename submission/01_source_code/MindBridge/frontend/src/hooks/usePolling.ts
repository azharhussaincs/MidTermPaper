import { useCallback, useEffect, useRef, useState } from 'react'

interface PollingState<T> {
  data: T | null
  error: unknown
  loading: boolean
  /** Fetch now (and restart the interval). Resolves with the fresh data. */
  refresh: () => Promise<T | null>
}

/**
 * Poll `fetcher` every `intervalMs`, pausing while the tab is hidden.
 * In-flight requests are aborted on unmount and when a newer request starts.
 */
export function usePolling<T>(fetcher: (signal: AbortSignal) => Promise<T>, intervalMs: number): PollingState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const fetcherRef = useRef(fetcher)
  const controllerRef = useRef<AbortController | null>(null)
  const timerRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    fetcherRef.current = fetcher
  }, [fetcher])

  const run = useCallback(async (): Promise<T | null> => {
    window.clearTimeout(timerRef.current)
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    try {
      const result = await fetcherRef.current(controller.signal)
      setData(result)
      setError(null)
      return result
    } catch (err) {
      if (controller.signal.aborted) return null
      setError(err)
      return null
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false)
        if (document.visibilityState === 'visible') {
          timerRef.current = window.setTimeout(() => void run(), intervalMs)
        }
      }
    }
  }, [intervalMs])

  useEffect(() => {
    void run()
    const onVisibility = () => {
      if (document.visibilityState === 'visible') void run()
      else window.clearTimeout(timerRef.current)
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.clearTimeout(timerRef.current)
      controllerRef.current?.abort()
    }
  }, [run])

  return { data, error, loading, refresh: run }
}
