import type {
  ApiErrorBody,
  AssessmentDetail,
  AssessmentListResponse,
  AssessmentTurnResponse,
  ClinicianQueueResponse,
  ClinicianReviewRequest,
  ClinicianReviewResponse,
  ListAssessmentsQuery,
  LLMConfigureRequest,
  SendMessageRequest,
  StartAssessmentRequest,
  SystemStatus,
} from '../types/api'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')

/** Every failed call rejects with this: the backend's `{error: {code, message, details}}` envelope, unwrapped. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  /** Field-level messages from a 422 `validation_error`, if any. */
  get fieldErrors(): { field: string; message: string }[] {
    return Array.isArray(this.details) ? (this.details as { field: string; message: string }[]) : []
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as ApiErrorBody).error?.message === 'string'
  )
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  query?: Record<string, string | number | string[] | undefined>
  signal?: AbortSignal
}

async function request<T>(path: string, { method = 'GET', body, query, signal }: RequestOptions = {}): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined) continue
    for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(key, String(item))
  }

  let response: Response
  try {
    response = await fetch(url, {
      method,
      signal,
      headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, 'network_error', `Can't reach the server at ${API_BASE_URL}. Is the backend running?`)
  }

  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    if (isErrorBody(payload)) {
      throw new ApiError(response.status, payload.error.code, payload.error.message, payload.error.details)
    }
    throw new ApiError(response.status, 'http_error', `Request failed (${response.status} ${response.statusText})`)
  }
  return payload as T
}

const enc = encodeURIComponent

export const api = {
  system: {
    status: (signal?: AbortSignal) => request<SystemStatus>('/api/system/status', { signal }),
    configureLLM: (body: LLMConfigureRequest) =>
      request<SystemStatus>('/api/system/llm/configure', { method: 'POST', body }),
  },
  assessments: {
    start: (body: StartAssessmentRequest) =>
      request<AssessmentDetail>('/api/assessments/start', { method: 'POST', body }),
    sendMessage: (sessionId: string, body: SendMessageRequest) =>
      request<AssessmentTurnResponse>(`/api/assessments/${enc(sessionId)}/message`, { method: 'POST', body }),
    finalize: (sessionId: string) =>
      request<AssessmentTurnResponse>(`/api/assessments/${enc(sessionId)}/finalize`, { method: 'POST' }),
    get: (sessionId: string, signal?: AbortSignal) =>
      request<AssessmentDetail>(`/api/assessments/${enc(sessionId)}`, { signal }),
    list: (query: ListAssessmentsQuery = {}, signal?: AbortSignal) =>
      request<AssessmentListResponse>('/api/assessments', {
        query: { status: query.status, limit: query.limit, offset: query.offset },
        signal,
      }),
  },
  clinician: {
    queue: (reviewedLimit = 20, signal?: AbortSignal) =>
      request<ClinicianQueueResponse>('/api/clinician/queue', { query: { reviewed_limit: reviewedLimit }, signal }),
    review: (sessionId: string, body: ClinicianReviewRequest) =>
      request<ClinicianReviewResponse>(`/api/clinician/${enc(sessionId)}/review`, { method: 'POST', body }),
  },
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}
