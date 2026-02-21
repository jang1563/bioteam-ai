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

// === Workflow Types ===

export type WorkflowState =
  | "PENDING"
  | "RUNNING"
  | "PAUSED"
  | "WAITING_HUMAN"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "OVER_BUDGET";

export type WorkflowTemplate = "direct_query" | "W1" | "W2" | "W3" | "W4" | "W5" | "W6";

export interface WorkflowStatus {
  id: string;
  template: string;
  state: WorkflowState;
  current_step: string;
  step_history: StepHistoryEntry[];
  budget_total: number;
  budget_remaining: number;
  loop_count: Record<string, number>;
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
  seed_papers?: string[];
}

export interface DirectQueryResponse {
  query: string;
  classification_type: "simple_query" | "needs_workflow";
  classification_reasoning: string;
  target_agent: string | null;
  workflow_type: string | null;
  answer: string | null;
  sources: Record<string, unknown>[];
  memory_context: Record<string, unknown>[];
  total_cost: number;
  total_tokens: number;
  model_versions: string[];
  duration_ms: number;
  timestamp: string;
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

// === Health ===

export interface HealthResponse {
  status: string;
  version: string;
  dependencies: Record<string, string>;
}
