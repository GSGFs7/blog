import { queryAllIncludingRoot } from "../dom";
import type { Behavior } from "../types";

export const CODE_PREVIEW_LINE_LIMIT = 12;

interface CodeMetrics {
  lineCount: number;
  lineHeight: number;
}

interface MountedExpander {
  target: HTMLElement;
  wrapper: HTMLDivElement;
}

// REFAC: poor performance
//  in "300+ lines code block * 7" real browser tests
//  it take 117ms:
//    UpdateLayoutTree * 6; total 69ms
//    Layout * 6; total 48ms
export function createCodeExpanderBehavior(): Behavior {
  const mounted = new WeakSet<HTMLElement>();
  const expanders = new Set<MountedExpander>();
  let nextId = 0;

  const mountTarget = (target: HTMLElement, expanderType: string, signal: AbortSignal) => {
    // do not change solid component
    if (mounted.has(target) || target.closest("[data-solid-island]")) {
      return;
    }

    const metrics = findCodeElements(target).map(measureCode);
    const lineCount = metrics.reduce((total, metric) => total + metric.lineCount, 0);
    if (lineCount <= CODE_PREVIEW_LINE_LIMIT) {
      mounted.add(target);
      return;
    }

    // `!target.parentNode` is unlikely to happen
    // it used by TypeScript type narrowing
    const parent = target.parentNode;
    if (!parent) {
      return;
    }

    const document = target.ownerDocument;
    const wrapper = document.createElement("div");
    const viewport = document.createElement("div");
    const button = document.createElement("button");
    let viewportId: string;
    // makesure id is unique
    do {
      viewportId = `code-preview-${++nextId}`;
    } while (document.getElementById(viewportId));

    wrapper.className = `code-expander code-expander--${expanderType} is-collapsed`;
    viewport.className = "code-expander__viewport";
    viewport.id = viewportId;
    viewport.style.setProperty(
      // viewport: `overflow: hidden;`
      "--code-preview-height",
      `${calculatePreviewHeight(target, metrics)}px`,
    );

    button.className = "code-expander__toggle";
    button.type = "button";
    button.setAttribute("aria-controls", viewportId);
    button.setAttribute("aria-expanded", "false");
    button.textContent = `expand (${lineCount} lines)`;

    // reorganize the DOM to:
    // wrapper.code-expander.is-collapsed
    // ├── viewport.code-expander__viewport
    // │   └── target
    // └── button
    parent.insertBefore(wrapper, target);
    viewport.appendChild(target); // move the target
    wrapper.append(viewport, button);

    button.addEventListener(
      "click",
      () => {
        const expanded = !wrapper.classList.toggle("is-collapsed");
        button.setAttribute("aria-expanded", String(expanded));
        button.textContent = expanded ? "collapse" : `expand (${lineCount} lines)`;
      },
      { signal },
    );

    mounted.add(target);
    expanders.add({ target, wrapper });
  };

  return {
    mount(root, context) {
      // init
      for (const expander of expanders) {
        if (!context.document.contains(expander.wrapper)) {
          expanders.delete(expander);
        }
      }

      // process terminal
      const terminals = queryAllIncludingRoot<HTMLElement>(root, ".markdown-body .terminal");
      for (const terminal of terminals) {
        mountTarget(terminal, "terminal", context.signal);
      }

      const codeBlocks = queryAllIncludingRoot<HTMLElement>(root, ".markdown-body pre");
      for (const codeBlock of codeBlocks) {
        if (codeBlock.closest(".terminal, .code-expander")) {
          continue;
        }

        mountTarget(codeBlock, "code", context.signal);
      }
    },
    destroy() {
      for (const { target, wrapper } of expanders) {
        const parent = wrapper.parentNode;
        if (!parent) {
          continue;
        }

        parent.insertBefore(target, wrapper);
        wrapper.remove();
      }
      expanders.clear();
    },
  };
}

function findCodeElements(target: HTMLElement): HTMLElement[] {
  if (target.tagName === "PRE") {
    const code = Array.from(target.children).find((child) => child.tagName === "CODE");
    return code instanceof HTMLElement ? [code] : [];
  }

  return Array.from(target.querySelectorAll<HTMLElement>("pre > code"));
}

function countLines(code: HTMLElement): number {
  const text = (code.textContent ?? "").replace(/\r\n?/g, "\n").replace(/\n$/, "");
  return text ? text.split("\n").length : 0;
}

function measureCode(code: HTMLElement): CodeMetrics {
  const pre = code.parentElement;
  const view = code.ownerDocument.defaultView;
  const style = pre && view ? view.getComputedStyle(pre) : undefined;
  const fontsize = Number.parseFloat(style?.fontSize ?? "") || 16;
  const lineHeight = Number.parseFloat(style?.lineHeight ?? "") || fontsize * 1.45;
  return {
    lineCount: countLines(code),
    lineHeight,
  };
}

function calculatePreviewHeight(target: HTMLElement, metrics: CodeMetrics[]): number {
  let remainingLines = CODE_PREVIEW_LINE_LIMIT;
  // content expanded height
  let fullTextHeight = 0;
  // content collapsed height
  let visibleTextHeight = 0;
  for (const metric of metrics) {
    const visibleLines = Math.min(metric.lineCount, remainingLines);
    visibleTextHeight += visibleLines * metric.lineHeight;
    remainingLines -= visibleLines;
    fullTextHeight += metric.lineCount * metric.lineHeight;
  }

  // add the part of not text
  const nonTextHeight = Math.max(0, target.scrollHeight - fullTextHeight);
  return Math.ceil(nonTextHeight + visibleTextHeight);
}
