import htmx from "htmx.org";
import "htmx-ext-head-support";
import "htmx-ext-preload";

import { setupHtmxPageLifecycle } from "./navigation/htmx-adapter";
import {
  readPageProtocol,
  readSessionStorage,
  syncHtmxHistoryGeneration,
} from "./navigation/protocol";
import { setupPageTransition } from "./page-transition";

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
setupPageTransition(document);

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

document.body.addEventListener("htmx:configRequest", (event) => {
  const csrfToken = getCsrfToken();
  if (!csrfToken) {
    return;
  }

  const detail = (event as CustomEvent).detail;
  detail.headers["X-CSRFToken"] = csrfToken;
});

window.htmx = htmx;
