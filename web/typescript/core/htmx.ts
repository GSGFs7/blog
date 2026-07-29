import htmx, { type HtmxBeforeSwapDetails } from "htmx.org";
import "htmx-ext-head-support";
import "htmx-ext-preload";

import { setupHtmxPageLifecycle } from "./navigation/htmx-adapter";
import {
  readPageProtocol,
  readSessionStorage,
  syncHtmxHistoryGeneration,
} from "./navigation/protocol";
import {
  applyHistoryPageTransition,
  applyPageTransition,
  type HtmxHistorySwapDetails,
} from "./page-transition";

// settings
htmx.config.includeIndicatorStyles = false;

declare global {
  interface Window {
    htmx: typeof htmx;
  }
}

// must match navigation protocol
const currentProtocol = readPageProtocol(document);
const sessionStorage = readSessionStorage(window);
if (sessionStorage) {
  syncHtmxHistoryGeneration(sessionStorage, currentProtocol);
}

// add plugin
setupHtmxPageLifecycle(document, { currentProtocol });

// get the csrf token from cookies
// double submit cookie
// a cookie in HTTP header(X-CSRFToken), a cookie in normal cookie header
// because cross site cookie isolation, it's safe if cookie match
const getCsrfToken = (): string | null => {
  return (
    document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="))
      ?.split("=")[1] ?? null
  );
};

const prefersReducedMotion = (): boolean =>
  document.defaultView?.matchMedia("(prefers-reduced-motion: reduce)").matches ?? false;

const applyHistoryTransition = (event: Event): void => {
  const detail = (event as CustomEvent<HtmxHistorySwapDetails>).detail;
  if (!detail) {
    return;
  }

  applyHistoryPageTransition(detail, document.body, prefersReducedMotion());
};

document.body.addEventListener("htmx:configRequest", (event) => {
  const csrfToken = getCsrfToken();
  if (!csrfToken) {
    return;
  }

  const detail = (event as CustomEvent).detail;
  detail.headers["X-CSRFToken"] = csrfToken;
});

// normal nav
document.body.addEventListener("htmx:beforeSwap", (event) => {
  const detail = (event as CustomEvent<HtmxBeforeSwapDetails>).detail;
  if (!detail) {
    return;
  }

  applyPageTransition(detail, document.body, prefersReducedMotion());
});
// history nav
document.body.addEventListener("htmx:historyCacheHit", applyHistoryTransition);
document.body.addEventListener("htmx:historyCacheMissLoad", applyHistoryTransition);

window.htmx = htmx;
