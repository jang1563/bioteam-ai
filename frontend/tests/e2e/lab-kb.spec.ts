import { test, expect } from "@playwright/test";
import { mockAllRoutes, MOCK_NEGATIVE_RESULTS } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockAllRoutes(page);
});

test.describe("Lab Knowledge Base Page", () => {
  test("renders heading and table", async ({ page }) => {
    await page.goto("/lab-kb");
    await expect(page.getByRole("heading", { name: /Lab Knowledge Base/i })).toBeVisible();
    // Table should be present
    await expect(page.locator("table")).toBeVisible({ timeout: 10_000 });
  });

  test("displays negative result entries", async ({ page }) => {
    await page.goto("/lab-kb");
    // First NR claim should be visible
    await expect(
      page.getByText(/siRNA knockdown of TP53/i),
    ).toBeVisible({ timeout: 10_000 });
    // Second NR claim
    await expect(
      page.getByText(/Metformin inhibits mTOR/i),
    ).toBeVisible();
  });

  test("shows source badges", async ({ page }) => {
    await page.goto("/lab-kb");
    await expect(page.getByText("internal").first()).toBeVisible({ timeout: 10_000 });
  });

  test("shows verification status", async ({ page }) => {
    await page.goto("/lab-kb");
    await expect(page.getByText("unverified").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("confirmed").first()).toBeVisible();
  });

  test("search input filters entries", async ({ page }) => {
    await page.goto("/lab-kb");
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.waitFor({ timeout: 10_000 });
    await searchInput.fill("Metformin");
    // Allow client-side filter to process
    await page.waitForTimeout(500);
    // Metformin entry should remain visible
    await expect(page.getByText(/Metformin inhibits mTOR/i)).toBeVisible();
  });

  test("add entry button is present", async ({ page }) => {
    await page.goto("/lab-kb");
    const addBtn = page.getByRole("button", { name: /Add Entry/i });
    await expect(addBtn).toBeVisible({ timeout: 10_000 });
  });

  test("result count badge is shown", async ({ page }) => {
    await page.goto("/lab-kb");
    await expect(page.getByText(/result/i).first()).toBeVisible({ timeout: 10_000 });
  });
});
