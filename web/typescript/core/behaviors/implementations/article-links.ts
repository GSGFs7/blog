import { queryAllIncludingRoot } from "../dom";
import type { Behavior } from "../types";

const selector = ".markdown-body a[href]";

function addRel(anchor: HTMLAnchorElement, value: string): void {
  const rel = new Set(anchor.rel.split(/\s+/).filter(Boolean));
  rel.add(value);
  anchor.rel = [...rel].join(" ");
}

function enhanceLink(anchor: HTMLAnchorElement, document: Document): void {
  const href = anchor.getAttribute("href")?.trim();
  if (
    !href ||
    href.startsWith("#") ||
    anchor.hasAttribute("download") ||
    anchor.closest("[data-solid-island]")
  ) {
    return;
  }

  let url: URL;
  try {
    url = new URL(href, document.baseURI);
  } catch {
    return;
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return;
  }

  // do not set target. let navigator decide what to do. (swap/reload)
  if (url.origin === document.location.origin) {
    return;
  }

  // respect the target explicitly declared
  const target = anchor.getAttribute("target")?.trim();
  if (!target) {
    anchor.target = "_blank";
  }
  if (!target || target.toLowerCase() === "_blank") {
    addRel(anchor, "noopener");
  }
}

export function createArticleLinkBehavior(): Behavior {
  return {
    mount(root, context) {
      for (const anchor of queryAllIncludingRoot<HTMLAnchorElement>(root, selector)) {
        enhanceLink(anchor, context.document);
      }
    },
  };
}
