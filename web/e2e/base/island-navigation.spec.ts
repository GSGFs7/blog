import { expect, test } from "@playwright/test";

test("cleans up and remounts Counter after history navigation", async ({ page }) => {
  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/test");

  const initialCounter = page.locator('[data-solid-island="Counter"]');
  const initialIncrement = initialCounter.getByRole("button", { name: "+1" });

  await expect(initialCounter.getByText("Count: 1024", { exact: true })).toBeVisible();
  await expect(initialIncrement).toHaveCount(1);
  await initialIncrement.click();
  await expect(initialCounter.getByText("Count: 1025", { exact: true })).toBeVisible();

  const aboutLink = page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true });

  await aboutLink.click();
  await expect(page).toHaveURL(/\/about$/);
  await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();
  await expect(page.locator('[data-solid-island="Counter"]')).toHaveCount(0);

  await page.goBack();
  await expect(page).toHaveURL(/\/test$/);

  const restoredCounter = page.locator('[data-solid-island="Counter"]');
  const restoredIncrement = restoredCounter.getByRole("button", { name: "+1" });
  await expect(restoredCounter.getByText("Count: 1024", { exact: true })).toBeVisible();
  await expect(restoredIncrement).toHaveCount(1);
  await restoredIncrement.click();
  await expect(restoredCounter.getByText("Count: 1025", { exact: true })).toBeVisible();

  expect(pageErrors).toEqual([]);
});
