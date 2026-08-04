import { queryAllIncludingRoot } from "../dom";
import type { Behavior } from "../types";

export type MediaQueryCallback = (matches: boolean) => void;

export const MOBILE_MEDIA_QUERY = "(max-width: 767px)";
const selector = "[data-mobile-undecorated]";

function updateDecoration(root: ParentNode, isMobile: boolean) {
  for (const element of queryAllIncludingRoot<HTMLElement>(root, selector)) {
    element.classList.toggle("is-decorated", !isMobile);
  }
}

function watchMediaQuery(callback: MediaQueryCallback, signal: AbortSignal): () => void {
  const mediaQuery = matchMedia(MOBILE_MEDIA_QUERY);
  const handleChange = (event: MediaQueryListEvent) => callback(event.matches);

  let stopped = false;
  const stop = () => {
    if (stopped) {
      return;
    }

    stopped = true;
    mediaQuery.removeEventListener("change", handleChange);
    signal.removeEventListener("abort", stop);
  };

  // listener targeted when width change
  // must check it immediately once
  callback(mediaQuery.matches);
  mediaQuery.addEventListener("change", handleChange);
  signal.addEventListener("abort", stop, { once: true });
  return stop;
}

export function createMobileDecorationBehavior(): Behavior {
  let isMobile = false;
  let mountedDocument: Document | undefined;
  let stopWatching: (() => void) | undefined;

  return {
    mount(root, context) {
      mountedDocument = context.document;
      const elements = queryAllIncludingRoot<HTMLElement>(root, selector);

      if (elements.length === 0) {
        if (!context.document.querySelector(selector)) {
          stopWatching?.();
          stopWatching = undefined;
        }
        return;
      }

      if (!stopWatching) {
        stopWatching = watchMediaQuery((matches) => {
          isMobile = matches;
          updateDecoration(context.document, isMobile);
        }, context.signal);
        return;
      }

      updateDecoration(root, isMobile);
    },
    destroy() {
      stopWatching?.();
      stopWatching = undefined;
      if (mountedDocument) {
        updateDecoration(mountedDocument, false);
      }
      mountedDocument = undefined;
      isMobile = false;
    },
  };
}
