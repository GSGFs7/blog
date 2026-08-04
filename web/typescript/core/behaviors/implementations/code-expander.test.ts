import { fireEvent } from "@solidjs/testing-library";
import { afterEach, expect, test } from "vitest";

import { runPageSwap } from "../../../test/page-lifecycle";
import { setupBehaviors } from "../manager";
import { waitForBehaviorMount } from "../test-utils";
import { CODE_PREVIEW_LINE_LIMIT } from "./code-expander";

let teardown: (() => void) | undefined;

function lines(count: number): string {
  return Array.from({ length: count }, (_, index) => `line ${index + 1}`).join("\n");
}

afterEach(() => {
  teardown?.();
  teardown = undefined;
  document.body.innerHTML = "";
});

test("collapses a long code block and toggles the full content", async () => {
  const lineCount = CODE_PREVIEW_LINE_LIMIT + 3;
  document.body.innerHTML = `
    <article class="markdown-body">
      <pre data-language="python"><code>${lines(lineCount)}</code></pre>
    </article>
  `;

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  const wrapper = document.querySelector(".code-expander")!;
  const viewport = document.querySelector<HTMLElement>(".code-expander__viewport")!;
  const button = document.querySelector<HTMLButtonElement>(".code-expander__toggle")!;

  expect(wrapper).toHaveClass("is-collapsed");
  expect(viewport.style.getPropertyValue("--code-preview-height")).toMatch(/px$/);
  expect(button).toHaveAttribute("aria-expanded", "false");
  expect(button).toHaveTextContent(`expand (${lineCount} lines)`);

  fireEvent.click(button);
  expect(wrapper).not.toHaveClass("is-collapsed");
  expect(button).toHaveAttribute("aria-expanded", "true");
  expect(button).toHaveTextContent("collapse");

  fireEvent.click(button);
  expect(wrapper).toHaveClass("is-collapsed");
  expect(button).toHaveAttribute("aria-expanded", "false");
});

test("leaves a short code block unchanged", async () => {
  document.body.innerHTML = `
    <article class="markdown-body">
      <pre><code>${lines(CODE_PREVIEW_LINE_LIMIT)}</code></pre>
    </article>
  `;

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(document.querySelector(".code-expander")).not.toBeInTheDocument();
  expect(document.querySelector("pre")).toHaveTextContent(`line ${CODE_PREVIEW_LINE_LIMIT}`);
});

test("collapses a terminal as one unit", async () => {
  document.body.innerHTML = `
    <article class="markdown-body">
      <div class="terminal">
        <div class="terminal-title">Terminal</div>
        <pre data-language="zsh"><code>${lines(8)}</code></pre>
        <pre data-language="output"><code>${lines(7)}</code></pre>
      </div>
    </article>
  `;

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(document.querySelectorAll(".code-expander")).toHaveLength(1);
  expect(document.querySelector(".code-expander")).toHaveClass("code-expander--terminal");
  expect(document.querySelector(".code-expander__toggle")).toHaveTextContent("expand (15 lines)");
});

test("mounts swapped content once and teardown restores the original markup", async () => {
  teardown = setupBehaviors();
  runPageSwap(() => {
    document.body.innerHTML = `
      <main id="swap-target">
        <article class="markdown-body">
          <pre><code>${lines(CODE_PREVIEW_LINE_LIMIT + 1)}</code></pre>
        </article>
      </main>
    `;
  });
  await waitForBehaviorMount();

  const target = document.getElementById("swap-target")!;
  expect(target.querySelectorAll(".code-expander")).toHaveLength(1);
  teardown();
  teardown = undefined;
  expect(target.querySelector(".code-expander")).not.toBeInTheDocument();
  expect(target.querySelector("article > pre")).toBeInTheDocument();
});
