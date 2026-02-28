// TypeScript types matching backend API models

// === Agent Types ===

export type AgentTier = "strategic" | "domain_expert" | "qa" | "engine";
export type ModelTier = "opus" | "sonnet" | "haiku";
export type AgentState = "idle" | "busy" | "unavailable" | "unknown";

export interface AgentListItem {
  id: string;
  name: string;
  tier: AgentTier;
  model_tier: ModelTier;
  criticality: "critical" | "optional";
  state: AgentState;
  total_calls: number;
  total_cost: number;
  consecutive_failures: number;
}

export interface AgentDetail extends AgentListItem {
  model_tier_secondary: ModelTier | null;
  division: string | null;
  tools: string[];
  mcp_access: string[];
  literature_access: boolean;
  version: string;
}

// === Agent Query & History Types ===

export interface AgentQueryRequest {
  query: string;
  context?: string;
}

export interface AgentQueryResponse {
  agent_id: string;
  answer: string;
  cost: number;
  duration_ms: number;
}

export interface AgentHistoryEntry {
  timestamp: string;
  workflow_id: string | null;
  step_id: string | null;
  cost: number;
  duration_ms: number;
  success: boolean;
  summary: string;
}

export interface AgentHistoryResponse {
  agent_id: string;
  entries: AgentHistoryEntry[];
  total_count: number;
  total_cost: number;
}

// === Workflow Types ===

export type WorkflowState =
  | "PENDING"
  | "RUNNING"
  | "PAUSED"
  | "WAITING_HUMAN"
  | "WAITING_DIRECTION"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "OVER_BUDGET";

export type WorkflowTemplate = "direct_query" | "W1" | "W2" | "W3" | "W4" | "W5" | "W6" | "W7" | "W8";

export interface WorkflowStatus {
  id: string;
  template: string;
  query: string;
  state: WorkflowState;
  current_step: string;
  step_history: StepHistoryEntry[];
  budget_total: number;
  budget_remaining: number;
  loop_count: Record<string, number>;
  session_manifest: Record<string, unknown>;
  citation_report: CitationReport;
  rcmxt_scores: RCMXTScore[];
}

// === Tier 1: Reproducibility & Evidence Scoring ===

export interface RCMXTScore {
  claim: string;
  R: number;
  C: number;
  M: number;
  X: number | null;
  T: number;
  composite: number | null;
  sources: string[];
  scorer_version: string;
  model_version: string;
}

export interface CitationIssue {
  type: "unverified" | "hallucinated" | "missing_doi";
  citation: string;
  detail: string;
}

export interface CitationReport {
  total_citations: number;
  verified: number;
  unverified: number;
  verification_rate: number;
  is_clean: boolean;
  issues: CitationIssue[];
}

export interface StepHistoryEntry {
  step_id?: string;
  agent_id?: string;
  status?: string;
  completed_at?: string;
  result_summary?: string;
  result_data?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface CreateWorkflowRequest {
  template: string;
  query: string;
  budget?: number;
  seed_papers?: string[];
  pdf_path?: string;  // W8: path to paper PDF/DOCX
}

export interface CreateWorkflowResponse {
  workflow_id: string;
  template: string;
  state: string;
  query: string;
}

export interface StepCheckpoint {
  step_id: string;
  status: string;
  agent_results: Record<string, unknown>[];
}

export type InterveneAction = "pause" | "resume" | "cancel" | "inject_note";
export type NoteAction = "ADD_PAPER" | "EXCLUDE_PAPER" | "MODIFY_QUERY" | "EDIT_TEXT" | "FREE_TEXT";

export interface InterveneRequest {
  action: InterveneAction;
  note?: string;
  note_action?: NoteAction;
}

// === Resume / Intervention API (resume.py) ===

export interface ResumeRequest {
  budget_topup?: number;
}

export interface ResumeResponse {
  workflow_id: string;
  new_state: string;
  budget_remaining: number;
}

export interface DirectionResponseRequest {
  response: string; // "continue" | "focus:GENE1,GENE2" | "skip_X" | "adjust:<text>"
}

export interface StepInjectRequest {
  result: Record<string, unknown>;
  reason: string;
}

export interface StepActionResponse {
  workflow_id: string;
  step_id: string;
  action: string;
  new_state?: string;
}

export interface InterveneResponse {
  workflow_id: string;
  action: string;
  new_state: string;
  detail: string;
}

// === Negative Results (Lab KB) Types ===

export type NRSource = "internal" | "clinical_trial" | "shadow" | "preprint_delta";
export type FailureCategory = "protocol" | "reagent" | "analysis" | "biological" | "";
export type VerificationStatus = "unverified" | "confirmed" | "rejected" | "ambiguous";

export interface NegativeResult {
  id: string;
  claim: string;
  outcome: string;
  source: NRSource;
  confidence: number;
  failure_category: FailureCategory;
  conditions: Record<string, unknown>;
  implications: string[];
  organism: string | null;
  source_id: string | null;
  created_at: string;
  created_by: string;
  verified_by: string | null;
  verification_status: VerificationStatus;
}

export interface CreateNegativeResultRequest {
  claim: string;
  outcome: string;
  source: NRSource;
  confidence?: number;
  failure_category?: FailureCategory;
  conditions?: Record<string, unknown>;
  implications?: string[];
  organism?: string;
  source_id?: string;
}

export interface UpdateNegativeResultRequest {
  claim?: string;
  outcome?: string;
  source?: NRSource;
  confidence?: number;
  failure_category?: FailureCategory;
  conditions?: Record<string, unknown>;
  implications?: string[];
  organism?: string;
  source_id?: string;
  verification_status?: VerificationStatus;
  verified_by?: string;
}

// === Direct Query Types ===

export interface DirectQueryRequest {
  query: string;
  conversation_id?: string | null;
  seed_papers?: string[];
}

export interface DirectQueryResponse {
  query: string;
  classification_type: "simple_query" | "needs_workflow";
  classification_reasoning: string;
  target_agent: string | null;
  workflow_type: string | null;
  routed_agent: string | null;
  conversation_id: string | null;
  answer: string | null;
  sources: Record<string, unknown>[];
  memory_context: Record<string, unknown>[];
  total_cost: number;
  total_tokens: number;
  model_versions: string[];
  duration_ms: number;
  timestamp: string;
}

// === Conversation Types ===

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  total_cost: number;
  turn_count: number;
}

export interface ConversationTurn {
  id: string;
  turn_number: number;
  query: string;
  classification_type: string;
  routed_agent: string | null;
  answer: string | null;
  sources: Record<string, unknown>[];
  cost: number;
  duration_ms: number;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  total_cost: number;
  turn_count: number;
  turns: ConversationTurn[];
}

// === Direct Query Streaming Types ===

export type StreamStatus = "idle" | "classifying" | "retrieving" | "streaming" | "done" | "error";

export interface StreamClassification {
  type: "simple_query" | "needs_workflow";
  reasoning: string;
  target_agent: string | null;
  workflow_type: string | null;
}

export interface StreamDoneData {
  classification_type?: string;
  target_agent?: string | null;
  workflow_type?: string | null;
  routed_agent: string | null;
  conversation_id?: string | null;
  answer?: string | null;
  total_cost: number;
  total_tokens: number;
  model_versions: string[];
  duration_ms: number;
  sources: Record<string, unknown>[];
}

// === SSE Types ===

export interface SSEEvent {
  event_type: string;
  workflow_id: string | null;
  step_id: string | null;
  agent_id: string | null;
  payload: Record<string, unknown>;
  timestamp: string | null;
}

// === Cold Start Types ===

export interface ColdStartRequest {
  seed_queries?: string[];
  pubmed_max_results?: number;
  s2_limit?: number;
  run_smoke_test?: boolean;
}

export interface SeedStepResult {
  source: string;
  query: string;
  papers_fetched: number;
  papers_stored: number;
  papers_skipped: number;
  errors: string[];
}

export interface SmokeCheckResult {
  name: string;
  passed: boolean;
  detail: string;
}

export interface ColdStartResponse {
  mode: "full" | "quick";
  success: boolean;
  seed_results: SeedStepResult[];
  smoke_checks: SmokeCheckResult[];
  collection_counts: Record<string, number>;
  total_papers_stored: number;
  duration_ms: number;
  timestamp: string;
  message: string;
}

export interface ColdStartStatus {
  is_initialized: boolean;
  agents_registered: number;
  critical_agents_healthy: boolean;
  collection_counts: Record<string, number>;
  total_documents: number;
  has_literature: boolean;
  has_lab_kb: boolean;
  timestamp: string;
}

// === Research Digest Types ===

export type DigestSchedule = "daily" | "weekly" | "manual";

export interface TopicScheduleInfo {
  topic_id: string;
  name: string;
  schedule: DigestSchedule;
  is_active: boolean;
  last_run_at: string | null;   // ISO-8601 UTC
  next_run_at: string | null;   // ISO-8601 UTC
  minutes_until_next: number | null;
  overdue: boolean;
}

export interface SchedulerStatus {
  enabled: boolean;
  running: boolean;
  check_interval_minutes: number;
  topics: TopicScheduleInfo[];
}
export type DigestSource = "pubmed" | "biorxiv" | "arxiv" | "github" | "huggingface" | "semantic_scholar";

export interface TopicProfile {
  id: string;
  name: string;
  queries: string[];
  sources: DigestSource[];
  categories: Record<string, string[]>;
  schedule: DigestSchedule;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateTopicRequest {
  name: string;
  queries: string[];
  sources?: DigestSource[];
  categories?: Record<string, string[]>;
  schedule?: DigestSchedule;
}

export interface UpdateTopicRequest {
  name?: string;
  queries?: string[];
  sources?: DigestSource[];
  categories?: Record<string, string[]>;
  schedule?: DigestSchedule;
  is_active?: boolean;
}

export interface DigestEntry {
  id: string;
  topic_id: string;
  source: DigestSource | "github";
  external_id: string;
  title: string;
  authors: string[];
  abstract: string;
  url: string;
  metadata_extra: Record<string, unknown>;
  relevance_score: number;
  fetched_at: string;
  published_at: string;
}

export interface DigestHighlight {
  title: string;
  source: string;
  one_liner: string;
  why_important?: string;
  url?: string;
}

export interface DigestReport {
  id: string;
  topic_id: string;
  period_start: string;
  period_end: string;
  entry_count: number;
  summary: string;
  highlights: DigestHighlight[];
  source_breakdown: Record<string, number>;
  cost: number;
  created_at: string;
}

export interface DigestStats {
  total_topics: number;
  total_entries: number;
  total_reports: number;
  entries_by_source: Record<string, number>;
}

// === Data Integrity Audit Types ===

export type IntegritySeverity = "info" | "warning" | "error" | "critical";
export type IntegrityCategory =
  | "gene_name_error"
  | "statistical_inconsistency"
  | "retracted_reference"
  | "corrected_reference"
  | "pubpeer_flagged"
  | "metadata_error"
  | "sample_size_mismatch"
  | "genome_build_inconsistency"
  | "p_value_mismatch"
  | "benford_anomaly"
  | "grim_failure"
  | "grimmer_sd_failure"
  | "grimmer_percent_failure"
  | "duplicate_image"
  | "image_manipulation"
  | "image_metadata_anomaly"
  | "image_quality_issue";
export type FindingStatus = "open" | "acknowledged" | "resolved" | "false_positive";

export interface AuditFinding {
  id: string;
  category: IntegrityCategory;
  severity: IntegritySeverity;
  title: string;
  description: string;
  source_text: string;
  suggestion: string;
  confidence: number;
  checker: string;
  finding_metadata: Record<string, unknown>;
  workflow_id: string | null;
  paper_doi: string | null;
  paper_pmid: string | null;
  status: FindingStatus;
  resolved_by: string | null;
  resolution_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface UpdateFindingRequest {
  status?: FindingStatus;
  resolved_by?: string;
  resolution_note?: string;
}

export interface TriggerAuditRequest {
  text: string;
  dois?: string[];
  use_llm?: boolean;
}

export interface AuditRun {
  id: string;
  workflow_id: string | null;
  trigger: string;
  total_findings: number;
  findings_by_severity: Record<string, number>;
  findings_by_category: Record<string, number>;
  overall_level: string;
  summary: string;
  cost: number;
  duration_ms: number;
  created_at: string;
}

export interface IntegrityStats {
  total_findings: number;
  findings_by_severity: Record<string, number>;
  findings_by_category: Record<string, number>;
  findings_by_status: Record<string, number>;
  total_runs: number;
  average_findings_per_run: number;
}

// === Health ===

export interface HealthCheck {
  status: string;
  detail: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  checks: Record<string, HealthCheck>;
  dependencies: Record<string, string>;
  timestamp: string;
}
