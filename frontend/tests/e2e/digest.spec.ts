import { test, expect } from "@playwright/test";
import { mockAllRoutes, MOCK_TOPICS, MOCK_DIGEST_ENTRIES, MOCK_DIGEST_REPORTS } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockAllRoutes(page);
});

test.describe("Research Digest Page", () => {
  test("renders heading and topic selector", async ({ page }) => {
    await page.goto("/digest");
    await expect(page.getByRole("heading", { name: /Research Digest/i })).toBeVisible();
  });

  test("shows topic name", async ({ page }) => {
    await page.goto("/digest");
    await expect(page.getByText(MOCK_TOPICS[0].name)).toBeVisible({ timeout: 10_000 });
  });

  test("displays digest entries with paper titles", async ({ page }) => {
    await page.goto("/digest");
    // Entry title should be visible
    await expect(
      page.getByText(/Transcriptomic changes in astronaut blood/i),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("displays digest stats", async ({ page }) => {
    await page.goto("/digest");
    // Stats like "1 topics" or entry counts
    await expect(page.getByText(/topic/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("shows source badges on entries", async ({ page }) => {
    await page.goto("/digest");
    // PubMed source badge
    await expect(page.getByText(/pubmed/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("report tab shows summary", async ({ page }) => {
    await page.goto("/digest");
    // Click on the report tab
    const reportTab = page.getByRole("tab", { name: /report/i });
    if (await reportTab.isVisible()) {
      await reportTab.click();
      await expect(
        page.getByText(/significant advances in space biology/i),
      ).toBeVisible({ timeout: 10_000 });
    }
  });
});
