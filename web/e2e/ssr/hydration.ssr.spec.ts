import { expect, test, type Page } from "@playwright/test";

async function openServerIsland(page: Page, path: string, name: string) {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const { promise, resolve } = Promise.withResolvers<void>();
  await page.route("**/web/typescript/index.tsx", async (route) => {
    await promise;
    await route.continue();
  });

  try {
    await page.goto(path, { waitUntil: "commit" });
    const island = page.locator(`[data-solid-island="${name}"]`);
    const root = island.locator(":scope > *");

    await expect(island).toHaveAttribute("data-solid-ssr", "");
    await root.evaluate((node) => {
      Object.assign(node, { renderedOnServer: true });
    });
    return { island, root, pageErrors };
  } finally {
    resolve();
  }
}

test("hydrates the server-rendered WIP island", async ({ page }) => {
  const { island, root, pageErrors } = await openServerIsland(page, "/entertainment", "WIP");
  const task = island.getByText(/^当前进度: /);
  const progress = island.locator(".h-2.animate-pulse");

  await expect(island.getByText("施工中")).toBeVisible();
  await expect(island.getByText("正在努力创建新文件夹")).toBeVisible();
  await expect(task).toHaveCount(1);

  const initialTask = await task.textContent();
  expect(initialTask).not.toBeNull();

  await page.waitForLoadState("domcontentloaded");
  await expect(task).not.toHaveText(initialTask!);
  await expect
    .poll(() => progress.evaluate((element) => Number.parseFloat(element.style.width)))
    .toBeGreaterThan(0);
  await expect(task).toHaveCount(1);
  await expect(root).toHaveJSProperty("renderedOnServer", true);
  expect(pageErrors).toEqual([]);
});

test("hydrates the server-rendered Counter with its template props", async ({ page }) => {
  const { island, root, pageErrors } = await openServerIsland(page, "/test", "Counter");

  await expect(island.getByText("Count: 1024", { exact: true })).toBeVisible();
  await island.getByRole("button", { name: "+1" }).click();
  await expect(island.getByText("Count: 1025", { exact: true })).toBeVisible();
  await expect(root).toHaveJSProperty("renderedOnServer", true);
  expect(pageErrors).toEqual([]);
});
