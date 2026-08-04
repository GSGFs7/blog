import { afterEach, expect, test } from "vitest";

import { runPageSwap } from "../../../test/page-lifecycle";
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

test("opens external article links in a new window", async () => {
  setArticle(`
    <a id="relative" href="/blog/other">relative</a>
    <a id="same-origin" href="${window.location.origin}/about">same origin</a>
    <a id="fragment" href="#section">fragment</a>
    <a id="external" href="https://outside.invalid/article">external</a>
    <a id="mailto" href="mailto:test@example.com">email</a>
    <a id="download" href="https://outside.invalid/file" download>download</a>
  `);

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(document.querySelector("#relative")).not.toHaveAttribute("target");
  expect(document.querySelector("#same-origin")).not.toHaveAttribute("target");
  expect(document.querySelector("#fragment")).not.toHaveAttribute("target");
  expect(document.querySelector("#mailto")).not.toHaveAttribute("target");
  expect(document.querySelector("#download")).not.toHaveAttribute("target");

  const external = document.querySelector("#external")!;
  expect(external).toHaveAttribute("target", "_blank");
  expect(external).toHaveAttribute("rel", "noopener");
});

test("preserves explicit targets and existing rel values", async () => {
  setArticle(`
    <a id="self" href="https://outside.invalid/self" target="_self">self</a>
    <a id="named" href="https://outside.invalid/named" target="preview">named</a>
    <a id="blank" href="https://outside.invalid/blank" target="_blank" rel="nofollow">blank</a>
  `);

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(document.querySelector("#self")).toHaveAttribute("target", "_self");
  expect(document.querySelector("#self")).not.toHaveAttribute("rel", "noopener");
  expect(document.querySelector("#named")).toHaveAttribute("target", "preview");
  expect(document.querySelector("#named")).not.toHaveAttribute("rel", "noopener");
  expect(document.querySelector("#blank")).toHaveAttribute("target", "_blank");
  expect(document.querySelector("#blank")).toHaveAttribute("rel", "nofollow noopener");
});

test("does not modify links inside solid islands", async () => {
  setArticle(`
    <div data-solid-island="Example">
      <a id="island-link" href="https://outside.invalid/island">island</a>
    </div>
  `);

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(document.querySelector("#island-link")).not.toHaveAttribute("target");
  expect(document.querySelector("#island-link")).not.toHaveAttribute("rel");
});

test("mounts links added after a page swap", async () => {
  teardown = setupBehaviors();

  runPageSwap(() => {
    setArticle('<a id="first" href="https://outside.invalid/first">first</a>');
  });
  await waitForBehaviorMount();
  expect(document.querySelector("#first")).toHaveAttribute("target", "_blank");

  runPageSwap(() => {
    setArticle('<a id="second" href="https://outside.invalid/second">second</a>');
  });
  await waitForBehaviorMount();
  expect(document.querySelector("#second")).toHaveAttribute("target", "_blank");
});
