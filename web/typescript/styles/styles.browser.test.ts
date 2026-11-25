import { afterEach, expect, test } from "vitest";

import { setupBehaviors } from "@/core/behaviors";

import "./globals.css";
import "./markdown.css";

let teardown: (() => void) | undefined;

afterEach(() => {
  teardown?.();
  teardown = undefined;
  document.body.replaceChildren();
  window.scrollTo(0, 0);
});

function styleOf(root: Element, selector: string, pseudo?: string) {
  const element = root.querySelector(selector);
  if (element === null) throw new Error(`Missing ${selector} inside ${root.tagName}`);
  return getComputedStyle(element, pseudo);
}

test("utilities override global and Markdown component defaults", () => {
  document.body.innerHTML = `
    <main class="site-main max-w-none pt-0"></main>
    <article class="markdown-body">
      <h1 class="text-[23px]">Heading</h1>
    </article>
    <div class="music-track rounded-none p-3.25"></div>
  `;

  const main = getComputedStyle(document.querySelector("main")!);
  expect(main.maxWidth).toBe("none");
  expect(main.paddingTop).toBe("0px");
  expect(getComputedStyle(document.querySelector("h1")!).fontSize).toBe("23px");
  const track = getComputedStyle(document.querySelector(".music-track")!);
  expect(track.borderRadius).toBe("0px");
  expect(track.padding).toBe("13px");
});

test.each(["article", "poem"])("%s prose styles stop at island internals", (layout) => {
  const content = `
    <h1>Heading</h1>
    <p><a href="#example">Link</a> <code>code</code></p>
    <ul><li>Item</li></ul>
    <pre><code>block</code></pre>
  `;
  document.body.innerHTML = `
    <article class="markdown-body markdown-body--${layout} is-decorated">
      <section id="prose">${content}</section>
      <section data-solid-island="Example">${content}</section>
    </article>
  `;

  const prose = document.querySelector("#prose")!;
  const island = document.querySelector("[data-solid-island]")!;

  expect(parseFloat(styleOf(prose, "p").marginBottom)).toBeGreaterThan(0);
  expect(styleOf(island, "p").marginBottom).toBe("0px");
  expect(styleOf(prose, "ul").listStyleType).toBe("disc");
  expect(styleOf(island, "ul").listStyleType).toBe("none");

  expect(styleOf(prose, "pre").backgroundColor).not.toBe("rgba(0, 0, 0, 0)");
  expect(styleOf(island, "pre").backgroundColor).toBe("rgba(0, 0, 0, 0)");

  expect(styleOf(prose, "a").color).not.toBe(styleOf(island, "a").color);
  expect(styleOf(island, "a").color).toBe(styleOf(island, "p").color);

  for (const selector of ["h1", "a", "p > code"]) {
    expect(styleOf(prose, selector, "::before").content).not.toBe("none");
    expect(styleOf(island, selector, "::before").content).toBe("none");
  }
});

test("Markdown image styles do not clobber island cover styles", () => {
  document.body.innerHTML = `
    <article class="markdown-body">
      <img id="prose-image" class="is-zoomable" alt="Prose">
      <span data-solid-island="MusicTrack">
        <div class="music-track"><button class="music-cover"><img class="is-zoomable" alt="Cover"></button></div>
      </span>
    </article>
  `;

  expect(getComputedStyle(document.querySelector("#prose-image")!).cursor).toBe("zoom-in");
  expect(getComputedStyle(document.querySelector(".music-cover img")!).cursor).not.toBe("zoom-in");
  expect(
    getComputedStyle(document.querySelector(".music-cover img")!).transitionProperty,
  ).toContain("filter");
});

test("zoomed image inside a spoiler escapes overflow clipping and article backdrop-filter", async () => {
  const svg =
    "data:image/svg+xml," +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><rect width="800" height="600" fill="#3b82f6"/></svg>',
    );
  document.body.innerHTML = `
    <article class="markdown-body backdrop-blur-lg" style="width: 320px; margin: 24px;">
      <details class="spoiler" open>
        <summary>spoiler</summary>
        <img id="spoiler-image" src="${svg}" alt="Spoiler" style="width: 160px; height: 120px;">
      </details>
    </article>
  `;

  const article = document.querySelector("article")!;
  const spoiler = document.querySelector<HTMLDetailsElement>("details.spoiler")!;
  const image = document.querySelector<HTMLImageElement>("#spoiler-image")!;
  if (!image.complete) {
    await new Promise<void>((resolve) => {
      image.addEventListener("load", () => resolve(), { once: true });
    });
  }

  const initialBackdrop = getComputedStyle(article).backdropFilter;
  expect(initialBackdrop).not.toBe("none");
  expect(getComputedStyle(spoiler).overflow).toBe("hidden");

  teardown = setupBehaviors();
  image.click();

  const clone = document.querySelector<HTMLImageElement>("img.zoom-image")!;
  expect(clone).not.toBeNull();
  expect(clone.parentElement).toBe(document.body);
  expect(getComputedStyle(image).visibility).toBe("hidden");
  expect(getComputedStyle(article).backdropFilter).toBe(initialBackdrop);

  clone.style.transition = "none";
  const spoilerRect = spoiler.getBoundingClientRect();
  const cloneRect = clone.getBoundingClientRect();
  expect(cloneRect.width).toBeGreaterThan(spoilerRect.width);
  expect(cloneRect.height).toBeGreaterThan(spoilerRect.height);

  const centerHit = document.elementFromPoint(
    cloneRect.left + cloneRect.width / 2,
    cloneRect.top + cloneRect.height / 2,
  );
  expect(centerHit).toBe(clone);
});

test("zoom clone stays aligned with the image while scrolling during close", async () => {
  const svg =
    "data:image/svg+xml," +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><rect width="800" height="600" fill="#3b82f6"/></svg>',
    );
  document.body.innerHTML = `
    <div style="height: 2000px; padding-top: 300px;">
      <article class="markdown-body" style="width: 320px; margin: 0 auto;">
        <img id="scroll-image" src="${svg}" alt="Scroll" style="width: 160px; height: 120px;">
      </article>
    </div>
  `;

  window.scrollTo(0, 150);
  const image = document.querySelector<HTMLImageElement>("#scroll-image")!;
  if (!image.complete) {
    await new Promise<void>((resolve) => {
      image.addEventListener("load", () => resolve(), { once: true });
    });
  }

  teardown = setupBehaviors();
  image.click();

  const clone = document.querySelector<HTMLImageElement>("img.zoom-image")!;
  expect(clone).not.toBeNull();

  window.scrollTo(0, 220);
  window.dispatchEvent(new Event("scroll"));
  clone.style.transition = "none";

  window.scrollTo(0, 320);
  const cloneRect = clone.getBoundingClientRect();
  const imageRect = image.getBoundingClientRect();
  expect(cloneRect.top).toBeCloseTo(imageRect.top, 1);
  expect(cloneRect.left).toBeCloseTo(imageRect.left, 1);
  expect(cloneRect.width).toBeCloseTo(imageRect.width, 1);
  expect(cloneRect.height).toBeCloseTo(imageRect.height, 1);
});
