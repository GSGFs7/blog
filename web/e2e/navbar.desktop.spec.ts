import { expect, test } from "@playwright/test";

const navigationItems = [
  { label: "Home", href: "/" },
  { label: "Blog", href: "/blog" },
  { label: "Entertainment", href: "/entertainment" },
  { label: "About", href: "/about" },
] as const;

test("shows desktop navigation", async ({ page }) => {
  await page.goto("/about");

  const navbar = page.locator(".site-navbar");
  const shell = page.locator(".site-navbar__shell");
  const desktopLinks = page.locator(".site-navbar__links");

  await expect(navbar).toBeVisible();
  await expect(navbar).toHaveCSS("position", "sticky");
  await expect(page.getByRole("button", { name: "打开导航菜单" })).toBeHidden();

  for (const item of navigationItems) {
    const link = desktopLinks.getByRole("link", { name: item.label, exact: true });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", item.href);
  }

  const backdropFilter = await shell.evaluate((element) => {
    const styles = window.getComputedStyle(element);
    return styles.backdropFilter || styles.getPropertyValue("-webkit-backdrop-filter");
  });
  expect(backdropFilter).toBe("blur(8px)");
});
