import { cleanup, render } from "@solidjs/testing-library";
import { afterEach, expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";

import MusicDock from "./MusicDock.island";
import { player } from "./player";

const cover =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="#6b8f6b"/></svg>',
  );

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  player.clear();
});

test("hovering the play button blurs the cover art behind it", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async () => {});
  render(() => <MusicDock />);
  player.play({ src: "https://example.com/song.mp3", coverUrl: cover, duration: 300 });
  const control = document.querySelector(".music-dock-control")!;
  const art = control.querySelector(".music-dock-art")!;
  expect(getComputedStyle(art).filter).toBe("none");
  await userEvent.hover(control);
  await vi.waitFor(() => expect(getComputedStyle(art).filter).toBe("blur(4px)"));
  if (matchMedia("(prefers-reduced-motion: no-preference)").matches) {
    await vi.waitFor(() => expect(getComputedStyle(art).transform).toMatch(/1\.1/));
  }
});

test("the buffering icon keeps spinning while the audio stalls", () => {
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => new Promise(() => {}));
  render(() => <MusicDock />);
  player.play({ src: "https://example.com/song.mp3", duration: 300 });
  const spinner = document.querySelector(".music-spin")!;
  expect(spinner).not.toBeNull();
  const [animation] = spinner.getAnimations() as CSSAnimation[];
  expect(animation.animationName).toBe("music-spin");
  expect(animation.effect?.getComputedTiming().iterations).toBe(Infinity);
  expect(animation.playState).toBe("running");
});

test("the hover zoom only runs when reduced motion is not preferred", () => {
  const styleRules = [...document.styleSheets]
    .flatMap((sheet) => [...sheet.cssRules])
    .flatMap((rule) => (rule instanceof CSSMediaRule ? [...rule.cssRules] : [rule]));
  const zoomRules = styleRules.filter(
    (rule): rule is CSSStyleRule =>
      rule instanceof CSSStyleRule && rule.style.transform.includes("scale(1.1)"),
  );
  expect(zoomRules.length).toBeGreaterThan(0);
  for (const rule of zoomRules) {
    expect(rule.parentRule).toBeInstanceOf(CSSMediaRule);
    const condition = (rule.parentRule as CSSMediaRule).conditionText;
    expect(condition).toContain("prefers-reduced-motion");
    expect(condition).toContain("no-preference");
  }
});
