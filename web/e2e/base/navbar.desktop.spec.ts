import { expect, test } from "@playwright/test";

const navigationItems = [
  { label: "Home", href: "/" },
  { label: "Blog", href: "/blog" },
  { label: "Entertainment", href: "/entertainment" },
  { label: "About", href: "/about" },
] as const;

test("shows desktop navigation links", async ({ page }) => {
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

test("shows a spinning loader until navigation completes", async ({ page }) => {
  let releaseResponse!: () => void;
  const responseGate = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  await page.route("**/about", async (route) => {
    await responseGate;
    await route.continue();
  });
  await page.goto("/test");
  await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();

  const logo = page.locator(".site-navbar__inner .site-navbar__brand-logo");
  const loader = page.locator(".site-navbar__inner .site-navbar__brand-loader");
  await expect(logo).toBeVisible();
  await expect(loader).toBeHidden();

  const navigation = page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true })
    .click();
  try {
    await expect(loader).toBeVisible();
    await expect(logo).toBeHidden();
    await expect(loader).toHaveCSS("animation-name", "navbar-loading-spin");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(loader).toHaveCSS("animation-name", "none");
  } finally {
    releaseResponse();
    await navigation;
  }

  await expect(page).toHaveURL(/\/about$/);
  await expect(logo).toBeVisible();
  await expect(loader).toBeHidden();
});
