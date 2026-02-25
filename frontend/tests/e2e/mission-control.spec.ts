import { test, expect } from "@playwright/test";
import { mockAllRoutes, MOCK_AGENTS, MOCK_WORKFLOWS } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockAllRoutes(page);
});

test.describe("Mission Control Page", () => {
  test("renders heading and agent grid", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Mission Control/i })).toBeVisible();
    // Agent section should show count
    await expect(page.getByText(/Agents/i).first()).toBeVisible({ timeout: 10_000 });
    // At least one agent name should appear somewhere
    await expect(page.getByText(/Research Director/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("renders workflow cards", async ({ page }) => {
    await page.goto("/");
    // Active Workflows heading
    await expect(page.getByText(/Workflows/i).first()).toBeVisible({ timeout: 10_000 });
    // Workflow template label should appear
    await expect(page.getByText("W1").first()).toBeVisible({ timeout: 10_000 });
  });

  test("shows workflow state badges", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/RUNNING/i).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/completed/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("cold start status shows initialized state", async ({ page }) => {
    await page.goto("/");
    // With is_initialized=true + critical_agents_healthy=true + has_literature=true,
    // the cold start banner should NOT show (fully initialized)
    await page.waitForTimeout(2000);
    // The banner is dismissed when fully initialized
    const banner = page.getByText("System not initialized");
    await expect(banner).not.toBeVisible();
  });

  test("activity feed section is visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Activity Feed/i)).toBeVisible();
  });
});
