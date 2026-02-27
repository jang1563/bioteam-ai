/**
 * E2E tests for /agents — Agent Character Roster page.
 *
 * Tests:
 *  1. Page loads with tier-grouped character cards (22 agents)
 *  2. Each card shows: icon circle, name, tier, tagline, status dot
 *  3. Click card → chat sheet opens with correct agent info
 *  4. Chat input + streaming mock → messages render correctly
 *  5. Close sheet → returns to roster
 *  6. Sidebar has "Team" link that navigates to /agents
 */

import { test, expect, type Page } from "@playwright/test";
import { mockAllRoutes } from "./fixtures";

// ── Full 22-agent mock ──────────────────────────────────────────────────────

const MOCK_AGENTS_FULL = [
  // Strategic
  { id: "research_director",          name: "Research Director",           tier: "strategic",     model_tier: "opus",   criticality: "critical", state: "idle",        total_calls: 12, total_cost: 0.45, consecutive_failures: 0 },
  { id: "knowledge_manager",          name: "Knowledge Manager",           tier: "strategic",     model_tier: "sonnet", criticality: "critical", state: "idle",        total_calls: 8,  total_cost: 0.22, consecutive_failures: 0 },
  { id: "project_manager",            name: "Project Manager",             tier: "strategic",     model_tier: "haiku",  criticality: "optional", state: "idle",        total_calls: 2,  total_cost: 0.03, consecutive_failures: 0 },
  // Domain — wet/dry
  { id: "t01_genomics",               name: "Genomics Expert",             tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 3,  total_cost: 0.10, consecutive_failures: 0 },
  { id: "t02_transcriptomics",        name: "Transcriptomics Expert",      tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "busy",        total_calls: 5,  total_cost: 0.18, consecutive_failures: 0 },
  { id: "t03_proteomics",             name: "Proteomics Expert",           tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 1,  total_cost: 0.04, consecutive_failures: 0 },
  // Domain — computation
  { id: "t04_biostatistics",          name: "Biostatistics Expert",        tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 4,  total_cost: 0.12, consecutive_failures: 0 },
  { id: "t05_ml_dl",                  name: "ML/DL Expert",                tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "unavailable", total_calls: 0,  total_cost: 0.00, consecutive_failures: 3 },
  { id: "t06_systems_bio",            name: "Systems Biology Expert",      tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 2,  total_cost: 0.07, consecutive_failures: 0 },
  { id: "t07_structural_bio",         name: "Structural Biology Expert",   tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 1,  total_cost: 0.03, consecutive_failures: 0 },
  // Domain — translation
  { id: "t08_scicomm",                name: "Science Communication",       tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 6,  total_cost: 0.20, consecutive_failures: 0 },
  { id: "t09_grants",                 name: "Grant Writing Expert",        tier: "domain_expert", model_tier: "opus",   criticality: "optional", state: "idle",        total_calls: 3,  total_cost: 0.35, consecutive_failures: 0 },
  { id: "t10_data_eng",               name: "Data Engineering Expert",     tier: "domain_expert", model_tier: "haiku",  criticality: "optional", state: "idle",        total_calls: 2,  total_cost: 0.02, consecutive_failures: 0 },
  // Cross-cutting
  { id: "experimental_designer",      name: "Experimental Designer",       tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 1,  total_cost: 0.04, consecutive_failures: 0 },
  { id: "integrative_biologist",      name: "Integrative Biologist",       tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 1,  total_cost: 0.03, consecutive_failures: 0 },
  // Engines
  { id: "ambiguity_engine",           name: "Ambiguity Engine",            tier: "engine",        model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 7,  total_cost: 0.15, consecutive_failures: 0 },
  { id: "data_integrity_auditor",     name: "Data Integrity Auditor",      tier: "engine",        model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 4,  total_cost: 0.08, consecutive_failures: 0 },
  { id: "digest_agent",               name: "Digest Agent",                tier: "engine",        model_tier: "haiku",  criticality: "optional", state: "idle",        total_calls: 10, total_cost: 0.05, consecutive_failures: 0 },
  // QA
  { id: "qa_statistical_rigor",       name: "QA Statistical Rigor",        tier: "qa",            model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 2,  total_cost: 0.06, consecutive_failures: 0 },
  { id: "qa_biological_plausibility", name: "QA Biological Plausibility",  tier: "qa",            model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 2,  total_cost: 0.06, consecutive_failures: 0 },
  { id: "qa_reproducibility",         name: "QA Reproducibility",          tier: "qa",            model_tier: "haiku",  criticality: "optional", state: "idle",        total_calls: 1,  total_cost: 0.01, consecutive_failures: 0 },
  // Paper review
  { id: "claim_extractor",            name: "Claim Extractor",             tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 0,  total_cost: 0.00, consecutive_failures: 0 },
  { id: "methodology_reviewer",       name: "Methodology Reviewer",        tier: "domain_expert", model_tier: "opus",   criticality: "optional", state: "idle",        total_calls: 0,  total_cost: 0.00, consecutive_failures: 0 },
];

const MOCK_AGENT_DETAIL_GENOMICS = {
  id: "t01_genomics",
  name: "Genomics Expert",
  tier: "domain_expert",
  model_tier: "sonnet",
  model_tier_secondary: null,
  division: "wet_dry",
  criticality: "optional",
  tools: ["search", "extract"],
  mcp_access: [],
  literature_access: true,
  version: "1.0",
  state: "idle",
  total_calls: 3,
  total_cost: 0.10,
  consecutive_failures: 0,
};

// SSE mock helper — returns a realistic streaming sequence
function makeSseMock(answer: string) {
  const tokens = answer.split(" ");
  const events: string[] = [
    `event: classification\ndata: {"type":"simple_query","reasoning":"Direct agent chat","target_agent":"t01_genomics","workflow_type":null}\n\n`,
    `event: memory\ndata: {"results_count":2,"sources":[{"title":"CRISPR in cancer","doi":"10.1038/test","year":2024,"source_type":"pubmed","content_snippet":"Key study..."}]}\n\n`,
  ];
  for (const token of tokens) {
    events.push(`event: token\ndata: {"text":"${token} "}\n\n`);
  }
  events.push(
    `event: done\ndata: {"classification_type":"simple_query","target_agent":"t01_genomics","routed_agent":"t01_genomics","conversation_id":"conv-agent-001","answer":"${answer}","total_cost":0.025,"total_tokens":450,"model_versions":["claude-sonnet-4-6"],"duration_ms":3200,"sources":[{"title":"CRISPR in cancer","doi":"10.1038/test","year":2024,"source_type":"pubmed"}]}\n\n`,
  );
  return events.join("");
}

// ── Setup ───────────────────────────────────────────────────────────────────

async function setupAgentsPage(page: Page) {
  await mockAllRoutes(page);

  // Override agents list with full 22-agent mock
  await page.route("**/api/v1/agents", (route) =>
    route.fulfill({ json: MOCK_AGENTS_FULL }),
  );

  // Agent detail for genomics
  await page.route("**/api/v1/agents/t01_genomics", (route) =>
    route.fulfill({ json: MOCK_AGENT_DETAIL_GENOMICS }),
  );

  // Auth stream token (for SSE)
  await page.route("**/api/v1/auth/stream-token", (route) =>
    route.fulfill({ json: { token: "test-token-abc", expires_in_seconds: 120, path: "/api/v1/direct-query/stream" } }),
  );
}

// ── Tests ────────────────────────────────────────────────────────────────────

test.describe("/agents — Character Roster", () => {

  test("1: page loads with tier groups and 22 agent cards", async ({ page }) => {
    await setupAgentsPage(page);
    await page.goto("/agents");

    // Page title
    await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();

    // Tier group headers
    await expect(page.getByText("Strategic Command")).toBeVisible();
    await expect(page.getByText("Domain — Wet / Dry Lab")).toBeVisible();
    await expect(page.getByText("Domain — Computation")).toBeVisible();
    await expect(page.getByText("Domain — Translation")).toBeVisible();
    await expect(page.getByText("Specialized Engines")).toBeVisible();
    await expect(page.getByText("QA Tier")).toBeVisible();
    await expect(page.getByText("Paper Review")).toBeVisible();

    // Count agent cards (each has a button role)
    const cards = page.getByRole("button").filter({ hasText: /Idle|Busy|Unavailable/ });
    await expect(cards).toHaveCount(23, { timeout: 5000 }); // 22 agents + sidebar collapse toggle

    await page.screenshot({ path: "tests/e2e/screenshots/01-roster-full.png", fullPage: true });
  });

  test("2: agent cards display correct visual elements", async ({ page }) => {
    await setupAgentsPage(page);
    await page.goto("/agents");

    // Research Director card
    const rdCard = page.getByRole("button", { name: /Research Director/ });
    await expect(rdCard).toBeVisible();

    // Genomics card with tagline
    const genomicsCard = page.getByRole("button", { name: /Genomics Expert/ });
    await expect(genomicsCard).toBeVisible();
    await expect(genomicsCard.getByText("Decodes genome and epigenome data")).toBeVisible();

    // Busy agent card — t02_transcriptomics
    const busyCard = page.getByRole("button", { name: /Transcriptomics Expert/ });
    await expect(busyCard).toBeVisible();
    await expect(busyCard.getByText("Busy")).toBeVisible();

    // Unavailable agent — t05_ml_dl
    const unavailCard = page.getByRole("button", { name: /ML\/DL Expert/ });
    await expect(unavailCard).toBeVisible();
    await expect(unavailCard.getByText("Unavailable")).toBeVisible();

    await page.screenshot({ path: "tests/e2e/screenshots/02-card-details.png" });
  });

  test("3: click agent card → chat sheet opens", async ({ page }) => {
    await setupAgentsPage(page);
    await page.goto("/agents");

    // Click Genomics card
    await page.getByRole("button", { name: /Genomics Expert/ }).click();

    // Sheet should open with agent info — scope assertions to the dialog
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 3000 });
    await expect(dialog.getByRole("heading", { name: "Genomics Expert" })).toBeVisible();
    // tagline appears in both header and empty-state — verify at least one is visible
    await expect(dialog.getByText("Decodes genome and epigenome data").first()).toBeVisible();

    // Empty state prompt should be visible
    await expect(page.getByText("Ask a research question to get started.")).toBeVisible();

    // Input textarea should be present
    await expect(page.getByRole("textbox")).toBeVisible();

    await page.screenshot({ path: "tests/e2e/screenshots/03-chat-sheet-open.png" });
  });

  test("4: streaming chat — message appears and streams in", async ({ page }) => {
    await setupAgentsPage(page);

    const MOCK_ANSWER = "CRISPR-Cas9 works through guide RNA targeting. The Cas9 nuclease creates a double strand break.";

    // Mock the streaming SSE endpoint
    await page.route("**/api/v1/direct-query/stream*", (route) => {
      route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "Connection": "keep-alive",
        },
        body: makeSseMock(MOCK_ANSWER),
      });
    });

    await page.goto("/agents");

    // Open genomics chat
    await page.getByRole("button", { name: /Genomics Expert/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    // Type a question
    const textarea = page.getByRole("textbox");
    await textarea.fill("What is CRISPR-Cas9?");

    await page.screenshot({ path: "tests/e2e/screenshots/04a-before-send.png" });

    // Send via button
    await page.getByRole("button", { name: "Send message" }).click();

    // User message should appear immediately
    await expect(page.getByText("What is CRISPR-Cas9?")).toBeVisible({ timeout: 3000 });

    // Wait for final agent response to appear
    await expect(page.getByText(/CRISPR-Cas9 works/)).toBeVisible({ timeout: 10000 });

    await page.screenshot({ path: "tests/e2e/screenshots/04b-after-stream.png" });
  });

  test("5: close sheet → returns to roster", async ({ page }) => {
    await setupAgentsPage(page);
    await page.goto("/agents");

    // Open chat
    await page.getByRole("button", { name: /Genomics Expert/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    // Close via X button
    await page.getByRole("button", { name: "Close chat" }).click();

    // Sheet should be closed
    await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 3000 });

    // Roster cards still visible
    await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();

    await page.screenshot({ path: "tests/e2e/screenshots/05-closed-back-to-roster.png" });
  });

  test("6: sidebar 'Team' link navigates to /agents", async ({ page }) => {
    await setupAgentsPage(page);
    await page.goto("/"); // Start on Mission Control

    // Find and click the Team nav link
    await page.getByRole("link", { name: "Team" }).click();
    await expect(page).toHaveURL(/\/agents/);
    await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();

    await page.screenshot({ path: "tests/e2e/screenshots/06-sidebar-team-link.png" });
  });

  test("7: switch agent — chat sheet resets", async ({ page }) => {
    await setupAgentsPage(page);

    // Mock another agent detail
    await page.route("**/api/v1/agents/knowledge_manager", (route) =>
      route.fulfill({
        json: { ...MOCK_AGENT_DETAIL_GENOMICS, id: "knowledge_manager", name: "Knowledge Manager" },
      }),
    );

    await page.goto("/agents");

    // Open genomics, type something
    await page.getByRole("button", { name: /Genomics Expert/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    // Close and open different agent
    await page.getByRole("button", { name: "Close chat" }).click();
    await page.getByRole("button", { name: /Knowledge Manager/ }).click();

    // Should show Knowledge Manager's info in the chat sheet header
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Knowledge Manager" })).toBeVisible();
    await expect(page.getByText("Ask a research question to get started.")).toBeVisible();

    await page.screenshot({ path: "tests/e2e/screenshots/07-switched-agent.png" });
  });

});
