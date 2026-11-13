/**
 * TypeScript mirrors of the FastAPI response/request models.
 *
 * Source of truth (keep in sync):
 *   backend/app/schemas/system.py      -> System* / LLM*
 *   backend/app/schemas/sessions.py    -> Assessment* / Queue* / Clinician*
 *   backend/app/schemas/assessment.py  -> domain models, RiskFlag, Inconsistency, AssessmentSummaryOutput
 *
 * Datetimes arrive as ISO-8601 strings in UTC.
 */

// ---------------------------------------------------------------------------
// Shared enums
// ---------------------------------------------------------------------------

export type ProviderName = 'auto' | 'local' | 'gemini'
export type ActiveProvider = 'local' | 'gemini'
export type AssessmentStatusName = 'in_progress' | 'awaiting_clinician_review' | 'reviewed' | 'interrupted'
export type RiskLevel = 'critical' | 'high' | 'elevated' | 'none'
export type FlagLevel = Exclude<RiskLevel, 'none'>
export type AssessmentDomain = 'mood' | 'stress' | 'sleep' | 'anxiety' | 'functioning' | 'concerns'
export type Severity = 'none' | 'mild' | 'moderate' | 'severe'
/** 0 = not at all, 1 = several days, 2 = more than half the days, 3 = nearly every day */
export type FrequencyScore = 0 | 1 | 2 | 3

export const ASSESSMENT_DOMAINS: readonly AssessmentDomain[] = [
  'mood',
  'stress',
  'sleep',
  'anxiety',
  'functioning',
  'concerns',
]

// ---------------------------------------------------------------------------
// System  (schemas/system.py)
// ---------------------------------------------------------------------------

export interface LLMStatus {
  active_provider: ActiveProvider | null
  configured_provider: ProviderName
  ollama_installed: boolean
  ollama_running: boolean
  local_model_available: boolean
  gemini_configured: boolean
  local_model: string
  gemini_model: string
  ollama_base_url: string
  local_setup: 'idle' | 'in_progress' | 'ready' | 'failed'
  local_setup_error: string | null
}

export interface TracingStatus {
  requested: boolean
  enabled: boolean
  project: string | null
}

export interface SystemStatus {
  status: 'ok' | 'degraded'
  app_env: string
  llm: LLMStatus
  tracing: TracingStatus
}

export interface LLMConfigureRequest {
  provider?: ProviderName | null
  /** Must match /^[\w.\-:/]+$/, 1-100 chars, e.g. "qwen2.5:7b" */
  local_model?: string | null
  ensure_local?: boolean
}

// ---------------------------------------------------------------------------
// Domain data  (schemas/assessment.py)
// ---------------------------------------------------------------------------

export interface MoodDomain {
  phq_little_interest?: FrequencyScore | null
  phq_feeling_down?: FrequencyScore | null
  overall_mood_rating?: number | null
  hopelessness_level?: Severity | null
  self_harm_thoughts?: boolean | null
  who5_items?: number[] | null
  mood_description?: string | null
}

export interface StressDomain {
  perceived_stress_level?: number | null
  stress_triggers?: string[] | null
  stress_duration?: 'days' | 'weeks' | 'months' | 'years' | null
  feels_overwhelmed?: boolean | null
  coping_strategies?: string[] | null
  notes?: string | null
}

export interface SleepDomain {
  average_sleep_hours?: number | null
  sleep_quality?: 'very_poor' | 'poor' | 'fair' | 'good' | 'very_good' | null
  reports_sleep_problems?: boolean | null
  difficulty_falling_asleep?: boolean | null
  frequent_night_waking?: boolean | null
  early_morning_waking?: boolean | null
  wakes_unrefreshed?: boolean | null
  excessive_daytime_sleepiness?: boolean | null
  sleeping_more_than_usual?: boolean | null
  notes?: string | null
}

export interface AnxietyDomain {
  gad_nervous_anxious?: FrequencyScore | null
  gad_uncontrollable_worry?: FrequencyScore | null
  panic_attacks?: 'none' | 'occasional' | 'frequent' | 'severe' | null
  physical_symptoms?: string[] | null
  cognitive_symptoms?: string[] | null
  avoidance_behaviours?: boolean | null
  notes?: string | null
}

export interface FunctioningDomain {
  work_study_impact?: Severity | null
  social_engagement?: 'normal' | 'reduced' | 'minimal' | 'isolated' | null
  energy_level?: number | null
  self_care?: 'maintained' | 'somewhat_neglected' | 'significantly_neglected' | null
  days_missed_last_month?: number | null
  notes?: string | null
}

export interface ConcernsDomain {
  narrative?: string | null
  main_challenges?: string[] | null
  support_goals?: string[] | null
  currently_receiving_support?: boolean | null
}

/**
 * `domain_data` is stored with nulls removed; `structured_assessment` inside a summary keeps
 * unanswered fields as null. Treat every field as optional and possibly null.
 */
export interface AssessmentDomainData {
  mood?: MoodDomain
  stress?: StressDomain
  sleep?: SleepDomain
  anxiety?: AnxietyDomain
  functioning?: FunctioningDomain
  concerns?: ConcernsDomain
}

export interface Inconsistency {
  code: string
  domains: AssessmentDomain[]
  description: string
  severity: 'low' | 'medium' | 'high'
}

export interface RiskFlag {
  code: string
  level: RiskLevel
  domain: AssessmentDomain
  evidence: string
  requires_immediate_escalation: boolean
  recommended_action: string
}

export interface CompletionStatus {
  percentage: number
  completed_domains: AssessmentDomain[]
  pending_domains: AssessmentDomain[]
  status: AssessmentStatusName
}

export interface AssessmentSummaryOutput {
  structured_assessment: AssessmentDomainData
  reported_concerns_summary: string
  /** Each entry starts with its audit tag: "[M1] ...", "[I1] ..." */
  missing_or_inconsistent_info: string[]
  /** Each entry starts with "[R#]"; critical/high entries contain "URGENT:" */
  areas_requiring_professional_review: string[]
  completion_status: CompletionStatus
  non_diagnostic_disclaimer: string
}

// ---------------------------------------------------------------------------
// Sessions  (schemas/sessions.py)
// ---------------------------------------------------------------------------

export interface StartAssessmentRequest {
  patient_alias?: string | null
  llm_provider?: ProviderName | null
}

export interface SendMessageRequest {
  /** 1-4000 characters after trimming */
  message: string
  llm_provider?: ProviderName | null
}

export interface DomainProgress {
  completed: boolean
  answered: number
  required: number
  percentage: number
}

export interface ChatMessage {
  id: string | null
  created_at: string | null
  role: 'user' | 'assistant' | 'tool' | (string & {})
  content: string
  tool_calls: string[] | null
  name: string | null
}

/** `interrupt()` payload of the clinician review gate (graph/nodes.py). */
export interface PendingReview {
  type: 'clinician_review'
  session_id: string
  patient_alias: string | null
  urgent: boolean
  summary: AssessmentSummaryOutput
  risk_flags: RiskFlag[]
  reflection_passed: boolean
  reflection_feedback: string | null
  early_submission: boolean
  missing_fields: string[]
  resume_with: Record<string, string>
}

/** `final_output` written by the review gate once a clinician signs off. */
export interface FinalOutput {
  session_id: string
  summary: AssessmentSummaryOutput
  ai_draft_summary: AssessmentSummaryOutput | null
  summary_revised_by_clinician: boolean
  urgent: boolean
  early_submission: boolean
  clinician_approved: boolean
  clinician_notes: string | null
  reviewed_at: string
}

/**
 * Backend declares `draft_summary`, `final_output`, `pending_review` and `clinical_summary`
 * as `dict`; their actual contents are the shapes typed here.
 */
export interface AssessmentTurnResponse {
  session_id: string
  /** False when the message was not processed (e.g. a clinician review is pending). */
  accepted: boolean
  reply: string
  replies: string[]
  status: AssessmentStatusName | null
  completion_pct: number
  domain_completion_map: Record<AssessmentDomain, DomainProgress>
  /** "domain.field" */
  missing_fields: string[]
  inconsistencies: Inconsistency[]
  risk_flags: RiskFlag[]
  requires_urgent_escalation: boolean
  assessment_complete: boolean
  awaiting_clinician_review: boolean
  draft_summary: AssessmentSummaryOutput | null
  final_output: FinalOutput | null
}

export interface AssessmentDetail extends AssessmentTurnResponse {
  patient_alias: string | null
  llm_provider: ProviderName | null
  messages: ChatMessage[]
  domain_data: AssessmentDomainData
  clinical_summary: AssessmentSummaryOutput | null
  pending_review: PendingReview | null
  reflection_passed: boolean | null
  reflection_attempts: number
  reflection_feedback: string | null
  finalize_requested: boolean
  clinician_reviewed: boolean
  clinician_notes: string | null
  created_at: string | null
  updated_at: string | null
}

export interface AssessmentListItem {
  session_id: string
  patient_alias: string | null
  status: AssessmentStatusName
  completion_pct: number
  risk_level: RiskLevel
  urgent: boolean
  created_at: string
  updated_at: string
}

export interface AssessmentListResponse {
  items: AssessmentListItem[]
  total: number
}

export interface ListAssessmentsQuery {
  status?: AssessmentStatusName[]
  limit?: number
  offset?: number
}

// ---------------------------------------------------------------------------
// Clinician  (schemas/sessions.py)
// ---------------------------------------------------------------------------

export interface QueueItem extends AssessmentListItem {
  early_submission: boolean
  top_risk_flags: string[]
  clinician_approved: boolean | null
}

export interface ClinicianQueueResponse {
  /** Urgent first, then by risk level, then oldest first. */
  awaiting_review: QueueItem[]
  recently_reviewed: QueueItem[]
}

export interface ClinicianReviewRequest {
  approved: boolean
  /** 1-10000 characters */
  clinician_notes: string
  revised_summary?: AssessmentSummaryOutput | null
}

export interface ClinicianReviewResponse {
  session_id: string
  status: AssessmentStatusName
  clinician_approved: boolean
  clinician_notes: string | null
  reviewed_at: string
  urgent: boolean
  early_submission: boolean
  summary_revised_by_clinician: boolean
  summary: AssessmentSummaryOutput
  ai_draft_summary: AssessmentSummaryOutput | null
}

// ---------------------------------------------------------------------------
// Errors  (core/exceptions.py)
// ---------------------------------------------------------------------------

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details: unknown
  }
}
