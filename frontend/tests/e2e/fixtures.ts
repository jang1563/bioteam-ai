import { type Page } from "@playwright/test";

// ── Mock data ──────────────────────────────────────────────

export const MOCK_AGENTS = [
  { id: "research_director", name: "Research Director", tier: "strategic", model_tier: "opus", criticality: "critical", state: "idle", total_calls: 12, total_cost: 0.45, consecutive_failures: 0 },
  { id: "knowledge_manager", name: "Knowledge Manager", tier: "strategic", model_tier: "sonnet", criticality: "critical", state: "idle", total_calls: 8, total_cost: 0.22, consecutive_failures: 0 },
  { id: "t01_genomics", name: "Genomics Expert", tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle", total_calls: 3, total_cost: 0.1, consecutive_failures: 0 },
];

export const MOCK_WORKFLOWS = [
  {
    id: "wf-001",
    template: "W1",
    query: "CRISPR gene editing in cancer therapy",
    state: "RUNNING",
    current_step: "SEARCH",
    step_history: [{ step_id: "SCOPE", agent_id: "research_director", status: "completed", completed_at: "2026-02-24T10:00:00Z", result_summary: "Scope defined" }],
    budget_total: 2.0,
    budget_remaining: 1.5,
    loop_count: {},
    session_manifest: {},
    citation_report: { total_citations: 0, verified: 0, unverified: 0, verification_rate: 0, is_clean: false, issues: [] },
    rcmxt_scores: [],
  },
  {
    id: "wf-002",
    template: "W1",
    query: "Space radiation effects on DNA repair",
    state: "COMPLETED",
    current_step: "REPORT",
    step_history: [
      { step_id: "SCOPE", status: "completed", completed_at: "2026-02-24T08:00:00Z" },
      { step_id: "SEARCH", status: "completed", completed_at: "2026-02-24T08:05:00Z" },
      { step_id: "REPORT", status: "completed", completed_at: "2026-02-24T08:30:00Z" },
    ],
    budget_total: 2.0,
    budget_remaining: 0.8,
    loop_count: {},
    session_manifest: {},
    citation_report: { total_citations: 15, verified: 14, unverified: 1, verification_rate: 0.93, is_clean: false, issues: [] },
    rcmxt_scores: [],
  },
];

export const MOCK_COLD_START_STATUS = {
  is_initialized: true,
  agents_registered: 20,
  critical_agents_healthy: true,
  collection_counts: { papers: 150, lab_kb: 12, conversations: 3 },
  total_documents: 165,
  has_literature: true,
  has_lab_kb: true,
  timestamp: "2026-02-24T10:00:00Z",
};

export const MOCK_HEALTH = {
  status: "healthy",
  version: "0.6.0",
  checks: {
    database: { status: "healthy", detail: "SQLite OK" },
    memory: { status: "healthy", detail: "ChromaDB OK" },
  },
  dependencies: { chromadb: "ok", sqlite: "ok", anthropic: "ok" },
  timestamp: "2026-02-24T10:00:00Z",
};

export const MOCK_CONVERSATIONS = [
  { id: "conv-001", title: "CRISPR mechanisms", created_at: "2026-02-24T09:00:00Z", updated_at: "2026-02-24T09:05:00Z", total_cost: 0.12, turn_count: 2 },
  { id: "conv-002", title: "Protein folding", created_at: "2026-02-23T14:00:00Z", updated_at: "2026-02-23T14:10:00Z", total_cost: 0.08, turn_count: 1 },
];

export const MOCK_CONVERSATION_DETAIL = {
  id: "conv-001",
  title: "CRISPR mechanisms",
  created_at: "2026-02-24T09:00:00Z",
  updated_at: "2026-02-24T09:05:00Z",
  total_cost: 0.12,
  turn_count: 2,
  turns: [
    {
      id: "turn-001",
      turn_number: 1,
      query: "What are the key mechanisms of CRISPR-Cas9?",
      classification_type: "simple_query",
      routed_agent: "t01_genomics",
      answer: "CRISPR-Cas9 works through a guide RNA that directs the Cas9 nuclease to a specific genomic location.",
      sources: [],
      cost: 0.06,
      duration_ms: 3200,
      created_at: "2026-02-24T09:00:00Z",
    },
  ],
};

export const MOCK_NEGATIVE_RESULTS = [
  {
    id: "nr-001",
    claim: "siRNA knockdown of TP53 increases apoptosis",
    outcome: "No significant change in apoptosis rate (p=0.45)",
    source: "internal",
    confidence: 0.85,
    failure_category: "biological",
    conditions: { cell_line: "HeLa", concentration: "50nM" },
    implications: ["TP53 pathway may be redundant in this cell line"],
    organism: "Homo sapiens",
    source_id: null,
    created_at: "2026-02-20T12:00:00Z",
    created_by: "manual",
    verified_by: null,
    verification_status: "unverified",
  },
  {
    id: "nr-002",
    claim: "Metformin inhibits mTOR in primary neurons",
    outcome: "mTOR activity unchanged at therapeutic doses",
    source: "clinical_trial",
    confidence: 0.72,
    failure_category: "protocol",
    conditions: {},
    implications: [],
    organism: "Mus musculus",
    source_id: "NCT0012345",
    created_at: "2026-02-18T08:00:00Z",
    created_by: "pipeline",
    verified_by: "reviewer1",
    verification_status: "confirmed",
  },
];

export const MOCK_TOPICS = [
  {
    id: "topic-001",
    name: "Space Biology",
    queries: ["spaceflight biology", "microgravity effects"],
    sources: ["pubmed", "biorxiv", "arxiv"],
    categories: {},
    schedule: "daily",
    is_active: true,
    created_at: "2026-02-20T10:00:00Z",
    updated_at: "2026-02-24T10:00:00Z",
  },
];

export const MOCK_DIGEST_ENTRIES = [
  {
    id: "entry-001",
    topic_id: "topic-001",
    source: "pubmed",
    external_id: "PMID:39000001",
    title: "Transcriptomic changes in astronaut blood cells during long-duration spaceflight",
    authors: ["Kim J", "Smith A", "Lee B"],
    abstract: "We analyzed RNA-seq data from astronaut blood samples collected during 6-month ISS missions.",
    url: "https://pubmed.ncbi.nlm.nih.gov/39000001/",
    metadata_extra: {},
    relevance_score: 0.92,
    fetched_at: "2026-02-24T06:00:00Z",
    published_at: "2026-02-20T00:00:00Z",
  },
];

export const MOCK_DIGEST_REPORTS = [
  {
    id: "report-001",
    topic_id: "topic-001",
    period_start: "2026-02-17T00:00:00Z",
    period_end: "2026-02-24T00:00:00Z",
    entry_count: 15,
    summary: "This week saw significant advances in space biology research.",
    highlights: [
      { title: "Transcriptomic changes in astronaut blood", source: "PubMed", one_liner: "RNA-seq reveals immune changes", why_important: "First large-scale study" },
    ],
    source_breakdown: { pubmed: 8, biorxiv: 4, arxiv: 3 },
    cost: 0.35,
    created_at: "2026-02-24T07:00:00Z",
  },
];

export const MOCK_DIGEST_STATS = {
  total_topics: 1,
  total_entries: 15,
  total_reports: 3,
  entries_by_source: { pubmed: 8, biorxiv: 4, arxiv: 3 },
};

// ── Route setup helpers ────────────────────────────────────

/** Mock all core API routes so pages render without a live backend. */
export async function mockAllRoutes(page: Page) {
  await page.route("**/api/v1/agents", (route) =>
    route.fulfill({ json: MOCK_AGENTS }),
  );
  await page.route("**/api/v1/workflows", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: MOCK_WORKFLOWS });
    }
    return route.fulfill({ json: { workflow_id: "wf-new", template: "W1", state: "PENDING", query: "test" } });
  });
  await page.route("**/api/v1/workflows/*", (route) =>
    route.fulfill({ json: MOCK_WORKFLOWS[0] }),
  );
  await page.route("**/api/v1/cold-start/status", (route) =>
    route.fulfill({ json: MOCK_COLD_START_STATUS }),
  );
  await page.route("**/health", (route) =>
    route.fulfill({ json: MOCK_HEALTH }),
  );
  await page.route("**/api/v1/conversations?*", (route) =>
    route.fulfill({ json: MOCK_CONVERSATIONS }),
  );
  await page.route("**/api/v1/conversations", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: MOCK_CONVERSATIONS });
    }
    return route.continue();
  });
  await page.route("**/api/v1/conversations/conv-001", (route) =>
    route.fulfill({ json: MOCK_CONVERSATION_DETAIL }),
  );
  await page.route("**/api/v1/negative-results*", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: MOCK_NEGATIVE_RESULTS });
    }
    if (route.request().method() === "POST") {
      return route.fulfill({
        json: { ...MOCK_NEGATIVE_RESULTS[0], id: "nr-new", claim: "New claim" },
      });
    }
    if (route.request().method() === "DELETE") {
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fulfill({ json: MOCK_NEGATIVE_RESULTS[0] });
  });
  await page.route("**/api/v1/digest/topics*", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: MOCK_TOPICS });
    }
    return route.fulfill({ json: MOCK_TOPICS[0] });
  });
  await page.route("**/api/v1/digest/entries*", (route) =>
    route.fulfill({ json: MOCK_DIGEST_ENTRIES }),
  );
  await page.route("**/api/v1/digest/reports*", (route) =>
    route.fulfill({ json: MOCK_DIGEST_REPORTS }),
  );
  await page.route("**/api/v1/digest/stats*", (route) =>
    route.fulfill({ json: MOCK_DIGEST_STATS }),
  );
  await page.route("**/api/v1/digest/run*", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  // SSE — return empty stream that stays open briefly
  await page.route("**/api/v1/sse*", (route) =>
    route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      body: "data: {}\n\n",
    }),
  );
}
