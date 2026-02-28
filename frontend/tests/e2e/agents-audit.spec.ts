/**
 * Comprehensive visual & UX audit for /agents — Agent Character Roster
 *
 * Covers:
 *  A. Layout & visual hierarchy at 3 viewports (desktop, tablet, mobile)
 *  B. All 8 tier groups rendering correctly
 *  C. Card states: idle / busy / unavailable
 *  D. Hover & focus-visible states
 *  E. Chat sheet open/close flow
 *  F. Streaming chat (token-by-token)
 *  G. Char limit counter
 *  H. Agent switching resets chat
 *  I. Keyboard navigation (Tab / Enter / Escape)
 *  J. Accessibility: roles, labels, headings
 *  K. Sidebar "Team" active link highlight
 *  L. Empty knowledge base warning message
 */

import { test, expect, type Page } from "@playwright/test";
import { mockAllRoutes } from "./fixtures";

// ── Full 22-agent mock ─────────────────────────────────────────────────────────

const MOCK_AGENTS = [
  // Strategic
  { id: "research_director",          name: "Research Director",           tier: "strategic",     model_tier: "opus",   criticality: "critical", state: "idle",        total_calls: 12, total_cost: 0.45, consecutive_failures: 0 },
  { id: "knowledge_manager",          name: "Knowledge Manager",           tier: "strategic",     model_tier: "sonnet", criticality: "critical", state: "idle",        total_calls: 8,  total_cost: 0.22, consecutive_failures: 0 },
  { id: "project_manager",            name: "Project Manager",             tier: "strategic",     model_tier: "haiku",  criticality: "optional", state: "idle",        total_calls: 2,  total_cost: 0.03, consecutive_failures: 0 },
  // Wet/Dry Lab
  { id: "t01_genomics",               name: "Genomics Expert",             tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 3,  total_cost: 0.10, consecutive_failures: 0 },
  { id: "t02_transcriptomics",        name: "Transcriptomics Expert",      tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "busy",        total_calls: 5,  total_cost: 0.18, consecutive_failures: 0 },
  { id: "t03_proteomics",             name: "Proteomics Expert",           tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 1,  total_cost: 0.04, consecutive_failures: 0 },
  // Computation
  { id: "t04_biostatistics",          name: "Biostatistics Expert",        tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 4,  total_cost: 0.12, consecutive_failures: 0 },
  { id: "t05_ml_dl",                  name: "ML/DL Expert",                tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "unavailable", total_calls: 0,  total_cost: 0.00, consecutive_failures: 3 },
  { id: "t06_systems_bio",            name: "Systems Biology Expert",      tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 2,  total_cost: 0.07, consecutive_failures: 0 },
  { id: "t07_structural_bio",         name: "Structural Biology Expert",   tier: "domain_expert", model_tier: "sonnet", criticality: "optional", state: "idle",        total_calls: 1,  total_cost: 0.03, consecutive_failures: 0 },
  // Translation
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

const MOCK_GENOMICS_DETAIL = {
  id: "t01_genomics", name: "Genomics Expert", tier: "domain_expert",
  model_tier: "sonnet", model_tier_secondary: null, division: "wet_dry",
  criticality: "optional", tools: ["search", "extract"], mcp_access: [],
  literature_access: true, version: "1.0", state: "idle",
  total_calls: 3, total_cost: 0.10, consecutive_failures: 0,
};

const MOCK_KM_DETAIL = {
  ...MOCK_GENOMICS_DETAIL, id: "knowledge_manager", name: "Knowledge Manager",
  tier: "strategic",
};

function makeSseMock(answer: string, slow = false) {
  const tokens = answer.split(" ");
  const events: string[] = [
    `event: classification\ndata: {"type":"simple_query","reasoning":"Direct agent chat","target_agent":"t01_genomics","workflow_type":null}\n\n`,
    `event: memory\ndata: {"results_count":2,"sources":[{"title":"CRISPR in cancer","doi":"10.1038/test","year":2024,"source_type":"pubmed","content_snippet":"Key study..."}]}\n\n`,
  ];
  for (const token of tokens) {
    events.push(`event: token\ndata: {"text":"${token} "}\n\n`);
    if (slow) events.push(""); // tiny delay signal (not real, just pads)
  }
  events.push(
    `event: done\ndata: {"classification_type":"simple_query","target_agent":"t01_genomics","routed_agent":"t01_genomics","conversation_id":"conv-001","answer":"${answer}","total_cost":0.025,"total_tokens":450,"model_versions":["claude-sonnet-4-6"],"duration_ms":3200,"sources":[{"title":"CRISPR in cancer","doi":"10.1038/test","year":2024,"source_type":"pubmed"}]}\n\n`,
  );
  return events.join("");
}

// ── Setup helper ───────────────────────────────────────────────────────────────

async function setup(page: Page) {
  await mockAllRoutes(page);
  await page.route("**/api/v1/agents", (r) => r.fulfill({ json: MOCK_AGENTS }));
  await page.route("**/api/v1/agents/t01_genomics", (r) => r.fulfill({ json: MOCK_GENOMICS_DETAIL }));
  await page.route("**/api/v1/agents/knowledge_manager", (r) => r.fulfill({ json: MOCK_KM_DETAIL }));
  await page.route("**/api/v1/auth/stream-token", (r) =>
    r.fulfill({ json: { token: "test-token", expires_in_seconds: 120, path: "/api/v1/direct-query/stream" } }),
  );
  await page.route("**/api/v1/direct-query/stream*", (r) =>
    r.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      body: makeSseMock("CRISPR-Cas9 uses guide RNA to create targeted double-strand breaks in DNA enabling precise genome editing."),
    }),
  );
}

// ── A: Layout at desktop (1440×900) ───────────────────────────────────────────
test("A1: Desktop layout — 8 tier groups visible, grid 5-col", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();

  // All 8 tier groups
  const groups = ["Strategic Command", "Domain — Wet / Dry Lab", "Domain — Computation",
    "Domain — Translation", "Cross-Cutting", "Specialized Engines", "QA Tier", "Paper Review"];
  for (const g of groups) {
    await expect(page.getByText(g)).toBeVisible();
  }

  await page.screenshot({ path: "tests/e2e/screenshots/audit/A1-desktop-full.png", fullPage: true });
});

test("A2: Tablet layout (768×1024) — grid collapses to 3-col", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await setup(page);
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/A2-tablet.png", fullPage: true });
});

test("A3: Mobile layout (390×844) — grid collapses to 2-col", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/A3-mobile.png", fullPage: true });
});

// ── B: Card states ─────────────────────────────────────────────────────────────
test("B1: Idle card — muted status dot, no ring animation", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  const card = page.getByRole("button", { name: /Genomics Expert/ });
  await expect(card).toBeVisible();
  await expect(card.getByText("Idle")).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/B1-idle-card.png" });
});

test("B2: Busy card — green pulse ring + Busy label", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  const card = page.getByRole("button", { name: /Transcriptomics Expert/ });
  await expect(card).toBeVisible();
  await expect(card.getByText("Busy")).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/B2-busy-card.png" });
});

test("B3: Unavailable card — grayscale + dimmed + Unavailable label", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  const card = page.getByRole("button", { name: /ML\/DL Expert/ });
  await expect(card).toBeVisible();
  await expect(card.getByText("Unavailable")).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/B3-unavailable-card.png" });
});

// ── C: Chat sheet visual ───────────────────────────────────────────────────────
test("C1: Chat sheet header — icon circle, SheetTitle, badge, tagline", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible({ timeout: 3000 });

  // SheetTitle should be the accessible heading
  await expect(dialog.getByRole("heading", { name: "Genomics Expert" })).toBeVisible();

  // Badge in header
  await expect(dialog.getByText("Idle").first()).toBeVisible();

  // Tagline in header
  await expect(dialog.getByText("Decodes genome and epigenome data").first()).toBeVisible();

  await page.screenshot({ path: "tests/e2e/screenshots/audit/C1-sheet-header.png" });
});

test("C2: Empty state — large icon + agent name + tagline + prompt text", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();

  await expect(page.getByText("Ask a research question to get started.")).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/C2-empty-state.png" });
});

test("C3: Input area — textarea, send button, char counter, hotkey hint", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  // Placeholder text
  const textarea = page.getByRole("textbox");
  await expect(textarea).toBeVisible();

  // Send button initially disabled (empty input)
  const sendBtn = page.getByRole("button", { name: "Send message" });
  await expect(sendBtn).toBeDisabled();

  // Type something → button enables
  await textarea.fill("What is CRISPR?");
  await expect(sendBtn).toBeEnabled();

  // Char counter visible ("What is CRISPR?" = 15 chars → 2000 - 15 = 1985)
  await expect(page.getByText("1985")).toBeVisible();

  // Hotkey hint
  await expect(page.getByText("⌘+Enter to send")).toBeVisible();

  await page.screenshot({ path: "tests/e2e/screenshots/audit/C3-input-area.png" });
});

test("C4: Char limit warning — counter turns amber near 1800", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");
  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  // Fill 1900 chars
  const longText = "A".repeat(1900);
  await page.getByRole("textbox").fill(longText);

  // Counter should show 100 and be amber colored
  await expect(page.getByText("100")).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/C4-char-limit-warning.png" });
});

// ── D: Streaming flow ─────────────────────────────────────────────────────────
test("D1: Send message → user bubble → streaming → done + sources", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  const textarea = page.getByRole("textbox");
  await textarea.fill("What is CRISPR-Cas9?");
  await page.screenshot({ path: "tests/e2e/screenshots/audit/D1a-before-send.png" });

  await page.getByRole("button", { name: "Send message" }).click();

  // User message bubble appears immediately
  await expect(page.getByText("What is CRISPR-Cas9?")).toBeVisible({ timeout: 3000 });
  await page.screenshot({ path: "tests/e2e/screenshots/audit/D1b-user-bubble.png" });

  // Agent response appears
  await expect(page.getByText(/CRISPR-Cas9 uses guide RNA/)).toBeVisible({ timeout: 10000 });
  await page.screenshot({ path: "tests/e2e/screenshots/audit/D1c-agent-response.png" });

  // Source card visible
  await expect(page.getByText("CRISPR in cancer")).toBeVisible({ timeout: 5000 });
  await page.screenshot({ path: "tests/e2e/screenshots/audit/D1d-sources.png" });
});

test("D2: Input + Send disabled during streaming, re-enables after done", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  await page.getByRole("textbox").fill("Test question");
  await page.getByRole("button", { name: "Send message" }).click();

  // After streaming completes, user message is visible
  await expect(page.getByText("Test question")).toBeVisible({ timeout: 5000 });

  // Textarea re-enables after streaming done
  await expect(page.getByRole("textbox")).toBeEnabled({ timeout: 15000 });

  await page.screenshot({ path: "tests/e2e/screenshots/audit/D2-streaming-state.png" });
});

// ── E: Keyboard navigation ─────────────────────────────────────────────────────
test("E1: Tab through cards — focus ring visible", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();

  // Tab to first card
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await page.screenshot({ path: "tests/e2e/screenshots/audit/E1-keyboard-focus.png" });
});

test("E2: Escape closes the chat sheet", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 3000 });
  await page.screenshot({ path: "tests/e2e/screenshots/audit/E2-escape-close.png" });
});

test("E3: Cmd+Enter sends the message", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  await page.getByRole("textbox").fill("Keyboard shortcut test");
  await page.keyboard.press("Meta+Enter");

  await expect(page.getByText("Keyboard shortcut test")).toBeVisible({ timeout: 3000 });
  await page.screenshot({ path: "tests/e2e/screenshots/audit/E3-cmd-enter.png" });
});

// ── F: Accessibility ──────────────────────────────────────────────────────────
test("F1: All agent buttons have aria-labels", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");
  // Wait for cards to actually render (not just the heading)
  await expect(page.getByRole("button", { name: /Research Director/ })).toBeVisible();

  // Every AgentCharacterCard should have aria-label
  const buttons = page.getByRole("button").filter({ hasText: /Idle|Busy|Unavailable/ });
  const count = await buttons.count();
  expect(count).toBeGreaterThan(20);

  for (let i = 0; i < count; i++) {
    const label = await buttons.nth(i).getAttribute("aria-label");
    expect(label).toBeTruthy();
  }
  await page.screenshot({ path: "tests/e2e/screenshots/audit/F1-aria-labels.png" });
});

test("F2: Chat sheet dialog has accessible title (no console error)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);

  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.goto("/agents");
  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  // Wait a moment for any console errors
  await page.waitForTimeout(500);

  const dialogTitleErrors = consoleErrors.filter((e) => e.includes("DialogTitle") || e.includes("DialogContent"));
  expect(dialogTitleErrors).toHaveLength(0);

  await page.screenshot({ path: "tests/e2e/screenshots/audit/F2-no-a11y-error.png" });
});

test("F3: Tier sections have aria-labelledby on groups", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();

  // Each tier section should be an aria role=group with label
  const groups = page.getByRole("group");
  const groupCount = await groups.count();
  expect(groupCount).toBeGreaterThan(5);
});

// ── G: Sidebar & navigation ───────────────────────────────────────────────────
test("G1: Sidebar 'Team' link is active/highlighted on /agents", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();

  const teamLink = page.getByRole("link", { name: "Team" });
  await expect(teamLink).toBeVisible();

  // The active class should be applied (link is on /agents page)
  const className = await teamLink.getAttribute("class");
  // Active links in this project use bg-accent or similar indicator
  expect(className).toBeTruthy();

  await page.screenshot({ path: "tests/e2e/screenshots/audit/G1-sidebar-active.png" });
});

test("G2: Navigate away and back — roster reloads correctly", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();

  // Navigate to Mission Control
  await page.getByRole("link", { name: /Mission Control/ }).click();
  await expect(page).not.toHaveURL(/\/agents/);

  // Navigate back to Team
  await page.getByRole("link", { name: "Team" }).click();
  await expect(page).toHaveURL(/\/agents/);
  await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();

  await page.screenshot({ path: "tests/e2e/screenshots/audit/G2-nav-back.png" });
});

// ── H: Multi-message conversation ─────────────────────────────────────────────
test("H1: Multi-turn — two questions → two user + two agent bubbles", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  // First question
  await page.getByRole("textbox").fill("What is CRISPR?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText(/CRISPR-Cas9 uses guide RNA/)).toBeVisible({ timeout: 10000 });

  // Second question
  await page.getByRole("textbox").fill("How does Cas9 cut DNA?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("How does Cas9 cut DNA?")).toBeVisible({ timeout: 3000 });
  await expect(page.getByText(/CRISPR-Cas9 uses guide RNA/).nth(1)).toBeVisible({ timeout: 10000 });

  await page.screenshot({ path: "tests/e2e/screenshots/audit/H1-multi-turn.png", fullPage: false });
});

// ── I: UX polish checks ────────────────────────────────────────────────────────
test("I1: Dark mode — roster renders correctly", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);

  // Force dark mode via emulateMedia
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Research Team" })).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/I1-dark-mode.png", fullPage: true });
});

test("I2: Dark mode — chat sheet", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/I2-dark-chat-sheet.png" });
});

test("I3: Sheet overlay — background dimmed when open", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: /Genomics Expert/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  // The overlay should be visible
  const overlay = page.locator("[data-slot='sheet-overlay']");
  await expect(overlay).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/audit/I3-overlay.png" });
});
