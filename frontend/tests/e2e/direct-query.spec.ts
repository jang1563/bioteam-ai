import { test, expect } from "@playwright/test";
import { mockAllRoutes, MOCK_CONVERSATIONS } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockAllRoutes(page);
});

test.describe("Direct Query Page", () => {
  test("renders heading and query textarea", async ({ page }) => {
    await page.goto("/query");
    await expect(page.getByRole("heading", { name: /Direct Query/i })).toBeVisible();
    await expect(page.locator("textarea").first()).toBeVisible({ timeout: 10_000 });
  });

  test("shows conversation list", async ({ page }) => {
    await page.goto("/query");
    await expect(page.getByText(/Conversations/i).first()).toBeVisible({ timeout: 10_000 });
    // Conversation titles should appear
    await expect(page.getByText(MOCK_CONVERSATIONS[0].title).first()).toBeVisible({ timeout: 10_000 });
  });

  test("clicking conversation loads its detail", async ({ page }) => {
    await page.goto("/query");
    // Wait for conversations to load then click the first one
    const convItem = page.getByText(MOCK_CONVERSATIONS[0].title);
    await convItem.waitFor({ timeout: 10_000 });
    await convItem.click();
    // The turn's query text should appear
    await expect(page.getByText(/key mechanisms of CRISPR/i)).toBeVisible({ timeout: 10_000 });
  });

  test("ask button is disabled when textarea is empty", async ({ page }) => {
    await page.goto("/query");
    const askBtn = page.getByRole("button", { name: /Ask/i });
    await askBtn.waitFor({ timeout: 10_000 });
    await expect(askBtn).toBeDisabled();
  });

  test("typing in textarea enables ask button", async ({ page }) => {
    await page.goto("/query");
    const textarea = page.locator("textarea").first();
    await textarea.waitFor({ timeout: 10_000 });
    await textarea.fill("What is gene therapy?");
    const askBtn = page.getByRole("button", { name: /Ask/i });
    await expect(askBtn).toBeEnabled();
  });

  test("shows character count", async ({ page }) => {
    await page.goto("/query");
    const textarea = page.locator("textarea").first();
    await textarea.waitFor({ timeout: 10_000 });
    await textarea.fill("Hello");
    await expect(page.getByText(/5\/2000/)).toBeVisible();
  });
});
