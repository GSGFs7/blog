import { afterEach, expect, test } from "vitest";

import "@/styles/markdown.css";
import { createAnnotationBehavior } from "./annotation";

let cleanup: (() => void) | undefined;

afterEach(() => {
  cleanup?.();
  document.body.replaceChildren();
});

test("annotation tooltip wraps within the viewport and stays clear of article clipping", () => {
  document.body.innerHTML = `<article class="markdown-body" style="position:fixed;right:0;top:0;overflow:hidden;width:100px;height:40px;filter:brightness(1)">
    <span class="md-note" data-note="${"一段较长的附加说明。".repeat(30)}" title="说明" tabindex="0">术语</span>
  </article>`;
  const controller = new AbortController();
  const behavior = createAnnotationBehavior();
  cleanup = () => {
    controller.abort();
    behavior.destroy?.();
  };
  behavior.mount(document.body, { document, signal: controller.signal });
  const note = document.querySelector<HTMLElement>(".md-note")!;
  const tooltip = document.querySelector<HTMLElement>('[role="tooltip"]')!;
  expect(getComputedStyle(note).textDecorationStyle).toBe("dashed");
  note.focus();
  const box = tooltip.getBoundingClientRect();
  expect(box.width).toBeGreaterThan(100);
  expect(box.left).toBeGreaterThanOrEqual(7);
  expect(box.right).toBeLessThanOrEqual(innerWidth - 7);
  expect(box.bottom).toBeLessThanOrEqual(innerHeight - 7);
  expect(tooltip.parentElement).toBe(document.body);
  expect(note.getAttribute("aria-describedby")).toBe(tooltip.id);
  note.click();
  expect(tooltip.hidden).toBe(false);
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  expect(tooltip.hidden).toBe(true);
});
