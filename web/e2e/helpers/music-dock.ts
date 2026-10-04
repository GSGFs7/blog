import { expect, test } from "@playwright/test";

function silentWave(): Buffer {
  const samples = 8_000 * 60;
  const wave = Buffer.alloc(44 + samples, 128);
  wave.write("RIFF", 0);
  wave.writeUInt32LE(36 + samples, 4);
  wave.write("WAVEfmt ", 8);
  wave.writeUInt32LE(16, 16);
  wave.writeUInt16LE(1, 20);
  wave.writeUInt16LE(1, 22);
  wave.writeUInt32LE(8_000, 24);
  wave.writeUInt32LE(8_000, 28);
  wave.writeUInt16LE(1, 32);
  wave.writeUInt16LE(8, 34);
  wave.write("data", 36);
  wave.writeUInt32LE(samples, 40);
  return wave;
}

export function musicDockNavigationTest(mode: "native" | "htmx", cacheMiss = false) {
  test(`music keeps playing across ${mode} navigation and history (${cacheMiss ? "cache miss" : "cache hit"}), then closes and reopens`, async ({
    page,
    context,
    browserName,
  }) => {
    if (browserName === "chromium") await context.grantPermissions(["local-network-access"]);
    const errors: Error[] = [];
    page.on("pageerror", (error) => errors.push(error));
    const wave = silentWave();
    await page.route(/\/dock-test.wav$/, (route) =>
      route.fulfill({ contentType: "audio/wav", body: wave }),
    );
    await page.route(/\/test$/, async (route) => {
      const response = await route.fetch();
      await route.fulfill({
        response,
        body: (await response.text()).replace(
          "</main>",
          '<div data-solid-island="MusicTrack" data-props=\'{"src":"/dock-test.wav"}\'></div></main>',
        ),
      });
    });
    await page.goto("/test");
    await expect(page.locator('meta[name="page-navigation-mode"]')).toHaveAttribute(
      "content",
      mode,
    );
    await expect(page.getByRole("button", { name: "play dock-test.wav" })).toBeEnabled();
    await expect(page.locator("#app-persistent-root")).toBeEmpty();
    await page.getByRole("button", { name: "play dock-test.wav" }).click();
    const audio = page.locator("#app-persistent-root audio");
    await expect
      .poll(() => audio.evaluate((element: HTMLAudioElement) => element.currentTime))
      .toBeGreaterThan(0);
    const original = await audio.elementHandle();
    const dock = page.getByRole("region", { name: "music player" });
    const beforeNavigation = await audio.evaluate(
      (element: HTMLAudioElement) => element.currentTime,
    );

    await page
      .locator(".site-navbar__links")
      .getByRole("link", { name: "About", exact: true })
      .click();
    await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
    await expect(page.locator('[data-solid-island="MusicTrack"]')).toHaveCount(0);
    expect(
      await original!.evaluate(
        (element) => element === document.querySelector("#app-persistent-root audio"),
      ),
    ).toBe(true);
    await expect
      .poll(() => audio.evaluate((element: HTMLAudioElement) => element.currentTime))
      .toBeGreaterThan(beforeNavigation);
    await expect(dock.getByRole("button", { name: "pause", exact: true })).toBeVisible();

    if (mode === "htmx") {
      await page.evaluate((clearCache) => {
        document.body.dataset.musicNavigationSource = "";
        document.addEventListener(
          "app:navigation-end",
          (event) => {
            document.body.dataset.musicNavigationSource = (event as CustomEvent).detail.source;
          },
          { once: true },
        );
        if (clearCache) sessionStorage.removeItem("htmx-history-cache");
      }, cacheMiss);
    }
    await page.goBack();
    await expect(page.getByRole("button", { name: "pause dock-test.wav" })).toBeVisible();
    if (mode === "htmx") {
      await expect(page.locator("body")).toHaveAttribute(
        "data-music-navigation-source",
        cacheMiss ? "fetch" : "cache",
      );
      if (cacheMiss) await page.evaluate(() => sessionStorage.removeItem("htmx-history-cache"));
    }
    await page.goForward();
    await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
    expect(
      await original!.evaluate(
        (element) => element === document.querySelector("#app-persistent-root audio"),
      ),
    ).toBe(true);
    expect(await audio.evaluate((element: HTMLAudioElement) => element.paused)).toBe(false);
    await expect(audio).toHaveCount(1);

    await dock.getByRole("button", { name: "pause", exact: true }).click();
    await expect(dock).toHaveCount(0);
    await expect(audio).not.toHaveAttribute("src");
    await page.goBack();
    await page.getByRole("button", { name: "play dock-test.wav" }).click();
    await expect(dock.getByRole("button", { name: "pause", exact: true })).toBeVisible();
    expect(
      await original!.evaluate(
        (element) => element === document.querySelector("#app-persistent-root audio"),
      ),
    ).toBe(true);
    await expect(audio).toHaveCount(1);
    expect(errors).toEqual([]);
  });
}
