import { expect, test } from "@playwright/test";

const navigationItems = [
  { label: "Home", href: "/" },
  { label: "Blog", href: "/blog" },
  { label: "Entertainment", href: "/entertainment" },
  { label: "About", href: "/about" },
] as const;

test.describe("mobile navigation", () => {
  test("opens and dismisses the menu", async ({ page }) => {
    await page.goto("/about");

    const desktopLinks = page.locator(".site-navbar__links");
    const menuButton = page.getByRole("button", { name: "打开导航菜单" });
    const mobileMenu = page.locator("#mobile-menu");

    await expect(desktopLinks).toBeHidden();
    await expect(menuButton).toBeVisible();
    await expect(mobileMenu).toBeHidden();

    await menuButton.click();
    await expect(mobileMenu).toBeVisible();
    await expect(mobileMenu).toHaveJSProperty("popover", "auto");

    for (const item of navigationItems) {
      const link = mobileMenu.getByRole("link", { name: item.label, exact: true });
      await expect(link).toBeVisible();
      await expect(link).toHaveAttribute("href", item.href);
    }

    await mobileMenu.getByRole("button", { name: "关闭导航菜单" }).click();
    await expect(mobileMenu).toBeHidden();

    await menuButton.click();
    await expect(mobileMenu).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(mobileMenu).toBeHidden();
  });

  test("navigates from a menu link", async ({ page }) => {
    await page.goto("/");

    const mobileMenu = page.locator("#mobile-menu");
    await page.getByRole("button", { name: "打开导航菜单" }).click();
    await expect(mobileMenu).toBeVisible();

    await mobileMenu.getByRole("link", { name: "About", exact: true }).click();

    await expect(page).toHaveURL(/\/about$/);
    await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();
    await expect(page.locator("#mobile-menu")).toBeHidden();
  });
});
