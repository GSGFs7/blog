import { afterEach, expect, test } from "vitest";

import { setupBehaviors } from "../manager";
import { waitForBehaviorMount } from "../test-utils";

let teardown: (() => void) | undefined;

function setArticle(html: string) {
  document.head.innerHTML = `<base href="${window.location.origin}/">`;
  document.body.innerHTML = `<article class="markdown-body">${html}</article>`;
}

afterEach(() => {
  teardown?.();
  teardown = undefined;
  document.head.innerHTML = "";
  document.body.innerHTML = "";
});

test("wraps emoji inside italics while keeping text", async () => {
  setArticle(`<p><em>斜体 🫡 文本</em></p>`);

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  const em = document.querySelector("em")!;
  const emoji = em.querySelector(".md-emoji")!;
  expect(emoji).not.toBeNull();
  expect(emoji?.textContent).toBe("🫡");
  expect(em.textContent).toBe("斜体 🫡 文本");
});

test("supports i elements, modifiers and ZWJ sequences", async () => {
  setArticle(`<p><i>wave 🏋🏽‍♀️ ok</i></p>`);

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  const emoji = document.querySelector("i .md-emoji")!;
  expect(emoji?.textContent).toBe("🏋🏽‍♀️");
  expect(document.querySelector("i")?.textContent).toBe("wave 🏋🏽‍♀️ ok");
});

test("leaves plain emoji outside italics untouched", async () => {
  setArticle(`<p>正文 🫡 结束</p><em>no emoji</em>`);

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(document.querySelector(".md-emoji")).toBeNull();
  expect(document.body.textContent).toContain("正文 🫡 结束");
});
