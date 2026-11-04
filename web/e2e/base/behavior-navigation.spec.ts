import { expect, test } from "@playwright/test";

test("remounts behaviors after enhanced navigation", async ({ page }) => {
  const pageErrors: Error[] = [];

  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/about");
  await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();
  await expect(page.locator("[data-blog-header]")).toHaveCount(0);

  await page.goto("/blog");
  const header = page.locator("[data-blog-header]");
  const image = page.locator("[data-blog-header-image]");
  await expect(header).toBeVisible();
  const initialDocument = await page.evaluateHandle(() => document);

  const initialTransform = await image.evaluate((element) => element.style.transform);
  const box = await header.boundingBox();
  if (!box) {
    throw new Error("Blog header has no bounding box");
  }
  await page.mouse.move(box.x + 4, box.y + 4);
  await expect
    .poll(() => image.evaluate((element) => element.style.transform))
    .not.toBe(initialTransform);

  await page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true })
    .click();
  await expect(page).toHaveURL(/\/about$/);
  await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();

  await page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "Blog", exact: true })
    .click();
  await expect(page).toHaveURL(/\/blog$/);
  await expect(header).toBeVisible();
  expect(await initialDocument.evaluate((original) => original === document)).toBe(true);

  const restoredTransform = await image.evaluate((element) => element.style.transform);
  const restoredBox = await header.boundingBox();
  if (!restoredBox) {
    throw new Error("Restored blog header has no bounding box");
  }
  await page.mouse.move(restoredBox.x + restoredBox.width - 4, restoredBox.y + 4);
  await expect
    .poll(() => image.evaluate((element) => element.style.transform))
    .not.toBe(restoredTransform);
  expect(pageErrors).toEqual([]);
});
