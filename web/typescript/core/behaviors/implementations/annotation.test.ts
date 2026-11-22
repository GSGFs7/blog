import { afterEach, expect, test, vi } from "vitest";

import { createAnnotationBehavior } from "./annotation";

let cleanup: (() => void) | undefined;

function mount() {
  document.body.innerHTML = `<article class="markdown-body">
    <span class="md-note" data-note="&lt;b&gt;纯文本&lt;/b&gt;" title="说明" tabindex="0">术语</span>
    <span data-note="第二条" tabindex="0">另一个</span>
    <div data-solid-island><span data-note="忽略">岛内</span></div>
  </article>`;
  const controller = new AbortController();
  const behavior = createAnnotationBehavior();
  const context = { document, signal: controller.signal };
  behavior.mount(document.body, context);
  cleanup = () => {
    controller.abort();
    behavior.destroy?.();
  };
  return {
    note: document.querySelector<HTMLElement>(".md-note")!,
    second: document.querySelectorAll<HTMLElement>("[data-note]")[1]!,
    tooltip: document.querySelector<HTMLElement>('[role="tooltip"]')!,
    remount: () => behavior.mount(document.body, context),
  };
}

afterEach(() => {
  cleanup?.();
  cleanup = undefined;
  document.body.innerHTML = "";
  vi.useRealTimers();
});

test("focus shows escaped text and Escape removes the accessible relationship", () => {
  const { note, tooltip } = mount();
  note.focus();
  expect(tooltip.hidden).toBe(false);
  expect(tooltip.textContent).toBe("<b>纯文本</b>");
  expect(tooltip.querySelector("b")).toBeNull();
  expect(note.getAttribute("aria-describedby")).toBe(tooltip.id);
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  expect(tooltip.hidden).toBe(true);
  expect(note.hasAttribute("aria-describedby")).toBe(false);
});

test("touch focus followed by click pins the tooltip and outside press dismisses it", () => {
  const { note, tooltip } = mount();
  note.focus();
  note.click();
  expect(tooltip.hidden).toBe(false);
  note.click();
  expect(tooltip.hidden).toBe(true);
  note.click();
  document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
  expect(tooltip.hidden).toBe(true);
});

test("hover stays open when the pointer enters the tooltip for selection", () => {
  vi.useFakeTimers();
  const { note, tooltip } = mount();
  note.dispatchEvent(new Event("pointerenter"));
  expect(tooltip.hidden).toBe(false);
  note.dispatchEvent(new Event("pointerleave"));
  tooltip.dispatchEvent(new Event("pointerenter"));
  vi.advanceTimersByTime(200);
  expect(tooltip.hidden).toBe(false);
  tooltip.dispatchEvent(new Event("pointerleave"));
  vi.advanceTimersByTime(200);
  expect(tooltip.hidden).toBe(true);
});

test("switching notes and repeated mounting leave only one active tooltip", () => {
  const { note, second, tooltip, remount } = mount();
  remount();
  note.click();
  expect(tooltip.hidden).toBe(false);
  second.click();
  expect(tooltip.textContent).toBe("第二条");
  expect(note.hasAttribute("aria-describedby")).toBe(false);
  expect(document.querySelectorAll('[role="tooltip"]')).toHaveLength(1);
  expect(document.querySelector("[data-solid-island] span")?.hasAttribute("aria-describedby")).toBe(
    false,
  );
  cleanup?.();
  expect(document.querySelector('[role="tooltip"]')).toBeNull();
  expect(note.getAttribute("title")).toBe("说明");
  expect(second.hasAttribute("aria-describedby")).toBe(false);
});

test("positioning keeps the tooltip inside the viewport near its edges", () => {
  const { note, tooltip } = mount();
  vi.spyOn(note, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    bottom: 20,
    width: 20,
  } as DOMRect);
  vi.spyOn(tooltip, "getBoundingClientRect").mockReturnValue({
    width: 240,
    height: 100,
  } as DOMRect);
  note.focus();
  expect(tooltip.style.left).toBe("8px");
  expect(tooltip.style.top).toBe("28px");
});

test("scrolling outside closes the tooltip while scrolling inside the tooltip keeps it open", () => {
  const { note, tooltip } = mount();
  note.click();
  expect(tooltip.hidden).toBe(false);

  tooltip.dispatchEvent(new Event("scroll"));
  tooltip.dispatchEvent(new WheelEvent("wheel", { bubbles: true }));
  expect(tooltip.hidden).toBe(false);

  document.dispatchEvent(new Event("scroll"));
  expect(tooltip.hidden).toBe(true);
  expect(note.hasAttribute("aria-describedby")).toBe(false);

  note.dispatchEvent(new Event("pointerenter"));
  expect(tooltip.hidden).toBe(false);
  note.dispatchEvent(new WheelEvent("wheel", { bubbles: true }));
  expect(tooltip.hidden).toBe(true);
});
