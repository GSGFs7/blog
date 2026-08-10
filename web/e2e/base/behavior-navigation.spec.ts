import { expect, test } from "@playwright/test";

const behaviorNames = ["blog-header", "code-expander", "mobile-decoration", "zoom"] as const;

function behaviorNameFromUrl(url: string): (typeof behaviorNames)[number] | undefined {
  const pathname = new URL(url).pathname;
  return behaviorNames.find(
    (name) =>
      pathname.includes(`/core/behaviors/${name}.`) ||
      pathname.includes(`/core/behaviors/implementations/${name}.`) ||
      pathname.includes(`/${name}-`),
  );
}

test("loads behavior chunks on demand and remounts after enhanced navigation", async ({ page }) => {
  const requestedBehaviors: string[] = [];
  const pageErrors: Error[] = [];

  page.on("request", (request) => {
    const name = behaviorNameFromUrl(request.url());
    if (name) {
      requestedBehaviors.push(name);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/about");
  await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();
  expect(requestedBehaviors).toEqual([]);

  await page.goto("/blog");
  const header = page.locator("[data-blog-header]");
  const image = page.locator("[data-blog-header-image]");
  await expect(header).toBeVisible();
  await expect.poll(() => requestedBehaviors.includes("blog-header")).toBe(true);
  expect(requestedBehaviors).toEqual(["blog-header"]);

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
  await expect(page.locator("[data-blog-header]")).toBeVisible();
  expect(requestedBehaviors).toEqual(["blog-header"]);
  expect(pageErrors).toEqual([]);
});
