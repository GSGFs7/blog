import { expect, test } from "@playwright/test";

test("hydrates the server-rendered WIP island", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/entertainment");

  const island = page.locator('[data-solid-island="WIP"]');
  const task = island.getByText(/^当前进度: /);
  const progress = island.locator(".h-2.animate-pulse");

  await expect(island).toHaveAttribute("data-solid-ssr", "");
  await expect(island.getByText("施工中")).toBeVisible();
  await expect(island.getByText("正在努力创建新文件夹")).toBeVisible();
  await expect(task).toHaveCount(1);

  const initialTask = await task.textContent();
  expect(initialTask).not.toBeNull();

  await expect(task).not.toHaveText(initialTask!, { timeout: 2_000 });
  await expect.poll(() => progress.evaluate((element) => element.style.width)).not.toBe("0px");
  await expect(task).toHaveCount(1);
  expect(pageErrors).toEqual([]);
});
