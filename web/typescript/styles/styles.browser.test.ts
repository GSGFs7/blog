import { afterEach, expect, test } from "vitest";

import "./globals.css";
import "./markdown.css";

afterEach(() => {
  document.body.replaceChildren();
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
    <div class="music-track rounded-none p-[13px]"></div>
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

test("Markdown image transitions do not clobber island cover transitions", () => {
  document.body.innerHTML = `
    <article class="markdown-body">
      <img id="prose-image" alt="Prose">
      <span data-solid-island="MusicTrack">
        <div class="music-track"><button class="music-cover"><img alt="Cover"></button></div>
      </span>
    </article>
  `;

  expect(getComputedStyle(document.querySelector("#prose-image")!).transitionProperty).toBe(
    "transform",
  );
  expect(
    getComputedStyle(document.querySelector(".music-cover img")!).transitionProperty,
  ).toContain("filter");
});

test("zoom disables the article backdrop filter and restores it on close", () => {
  document.body.innerHTML = `
    <article class="markdown-body backdrop-blur-lg"><img alt="Prose"></article>
  `;
  const article = document.querySelector("article")!;
  const image = document.querySelector("img")!;
  const initial = getComputedStyle(article).backdropFilter;
  expect(initial).not.toBe("none");
  image.classList.add("is-zoomed");
  expect(getComputedStyle(article).backdropFilter).toBe("none");
  image.classList.remove("is-zoomed");
  expect(getComputedStyle(article).backdropFilter).toBe(initial);
});
