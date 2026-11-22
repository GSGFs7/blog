import { queryAllIncludingRoot } from "../dom";
import type { Behavior, BehaviorContext } from "../types";

const NOTE_SELECTOR = ".markdown-body [data-note]";
const INTERACTIVE_SELECTOR = "a, button, input, [data-solid-island]";
const VIEWPORT_MARGIN = 8;
const CLOSE_DELAY_MS = 150;

let nextId = 0;

interface ActiveNote {
  element: HTMLElement;
  pinned: boolean;
}

export function createAnnotationBehavior(): Behavior {
  const enhanced = new Map<HTMLElement, string | null>();
  let context: BehaviorContext | undefined;
  let tooltip: HTMLDivElement | undefined;
  let active: ActiveNote | undefined;
  let closeTimer: ReturnType<typeof setTimeout> | undefined;
  let openController: AbortController | undefined;

  const cancelClose = () => {
    clearTimeout(closeTimer);
    closeTimer = undefined;
  };

  const reposition = () => {
    const view = context?.document.defaultView;
    if (!active || !tooltip || !view) {
      return;
    }
    positionTooltip(tooltip, active.element, view);
  };

  const close = () => {
    cancelClose();
    openController?.abort();
    openController = undefined;

    if (active && tooltip) {
      removeDescribedBy(active.element, tooltip.id);
      active.element.removeAttribute("data-state");
    }
    active = undefined;

    if (tooltip) {
      tooltip.hidden = true;
    }
  };

  const scheduleClose = (source?: HTMLElement) => {
    if (source && active?.element !== source) {
      return;
    }

    cancelClose();
    closeTimer = setTimeout(() => {
      if (active && !active.pinned && context?.document.activeElement !== active.element) {
        close();
      }
    }, CLOSE_DELAY_MS);
  };

  const attachOpenListeners = (doc: Document) => {
    openController?.abort();
    openController = new AbortController();
    const { signal } = openController;

    const closeOnExternalScroll = (event: Event) => {
      const target = event.target instanceof Node ? event.target : null;
      if (target && tooltip?.contains(target)) {
        return;
      }
      close();
    };

    doc.addEventListener(
      "pointerdown",
      (event) => {
        const target = event.target instanceof Node ? event.target : null;
        if (target && !active?.element.contains(target) && !tooltip?.contains(target)) {
          close();
        }
      },
      { signal },
    );
    doc.addEventListener(
      "keydown",
      (event) => {
        if (event.key === "Escape") {
          close();
        }
      },
      { signal },
    );
    doc.addEventListener("scroll", closeOnExternalScroll, { signal, capture: true });
    doc.addEventListener("wheel", closeOnExternalScroll, { signal, passive: true });
    doc.defaultView?.addEventListener("resize", reposition, { signal });
  };

  const open = (element: HTMLElement, pinned = false) => {
    cancelClose();
    if (!tooltip || !context) {
      return;
    }

    const isSameElement = active?.element === element;
    if (!isSameElement) {
      close();
      attachOpenListeners(context.document);
    }

    active = { element, pinned: pinned || (isSameElement && Boolean(active?.pinned)) };
    tooltip.textContent = element.dataset.note ?? "";
    tooltip.hidden = false;
    addDescribedBy(element, tooltip.id);
    element.dataset.state = "open";
    reposition();
  };

  const ensureTooltip = (behaviorContext: BehaviorContext) => {
    if (tooltip && behaviorContext.document.contains(tooltip)) {
      return;
    }

    tooltip = createTooltipElement(behaviorContext.document);
    behaviorContext.document.body.append(tooltip);

    const options = { signal: behaviorContext.signal };
    tooltip.addEventListener("pointerenter", cancelClose, options);
    tooltip.addEventListener("pointerleave", () => scheduleClose(), options);
    behaviorContext.signal.addEventListener("abort", close, { once: true });
  };

  const bindNote = (element: HTMLElement, signal: AbortSignal) => {
    if (enhanced.has(element)) {
      return;
    }

    enhanced.set(element, element.getAttribute("title"));
    element.removeAttribute("title");

    const options = { signal };
    element.addEventListener(
      "pointerenter",
      (event) => {
        if (event.pointerType !== "touch") {
          open(element);
        }
      },
      options,
    );
    element.addEventListener("pointerleave", () => scheduleClose(element), options);
    element.addEventListener("focus", () => open(element), options);
    element.addEventListener("blur", () => scheduleClose(element), options);
    element.addEventListener(
      "click",
      (event) => {
        if (shouldIgnoreClick(event.target, element)) {
          return;
        }
        if (active?.element === element && active.pinned) {
          close();
        } else {
          open(element, true);
        }
      },
      options,
    );
  };

  return {
    mount(root, behaviorContext) {
      context = behaviorContext;
      if (active && !behaviorContext.document.contains(active.element)) {
        close();
      }

      const notes = findNotes(root);
      if (!notes.length) {
        return;
      }

      ensureTooltip(behaviorContext);
      for (const note of notes) {
        bindNote(note, behaviorContext.signal);
      }
    },
    destroy() {
      close();
      tooltip?.remove();
      tooltip = undefined;
      for (const [element, title] of enhanced) {
        if (title !== null) {
          element.setAttribute("title", title);
        }
      }
      enhanced.clear();
      context = undefined;
    },
  };
}

function findNotes(root: ParentNode): HTMLElement[] {
  return queryAllIncludingRoot<HTMLElement>(root, NOTE_SELECTOR).filter(
    (element) => !element.closest("[data-solid-island]") && Boolean(element.dataset.note?.trim()),
  );
}

function createTooltipElement(doc: Document): HTMLDivElement {
  const element = doc.createElement("div");
  do {
    element.id = `md-note-tooltip-${++nextId}`;
  } while (doc.getElementById(element.id));
  element.className = "md-note__tooltip";
  element.setAttribute("role", "tooltip");
  element.hidden = true;
  return element;
}

function addDescribedBy(element: HTMLElement, id: string): void {
  const ids = new Set(
    (element.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean),
  );
  ids.add(id);
  element.setAttribute("aria-describedby", [...ids].join(" "));
}

function removeDescribedBy(element: HTMLElement, id: string): void {
  const ids = (element.getAttribute("aria-describedby") ?? "")
    .split(/\s+/)
    .filter((token) => token && token !== id);
  if (ids.length) {
    element.setAttribute("aria-describedby", ids.join(" "));
  } else {
    element.removeAttribute("aria-describedby");
  }
}

function positionTooltip(tooltip: HTMLElement, anchor: HTMLElement, view: Window): void {
  const anchorRect = anchor.getBoundingClientRect();
  const boxRect = tooltip.getBoundingClientRect();
  const left = clamp(
    anchorRect.left + (anchorRect.width - boxRect.width) / 2,
    VIEWPORT_MARGIN,
    view.innerWidth - boxRect.width - VIEWPORT_MARGIN,
  );
  const above = anchorRect.top - boxRect.height - VIEWPORT_MARGIN;
  const preferredTop = above >= VIEWPORT_MARGIN ? above : anchorRect.bottom + VIEWPORT_MARGIN;
  const top = clamp(
    preferredTop,
    VIEWPORT_MARGIN,
    view.innerHeight - boxRect.height - VIEWPORT_MARGIN,
  );
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(value, max));
}

function shouldIgnoreClick(target: EventTarget | null, note: HTMLElement): boolean {
  if (!(target instanceof Element)) {
    return true;
  }
  return target.closest("[data-note]") !== note || target.closest(INTERACTIVE_SELECTOR) !== null;
}
