import type { PageNavigationDeliverySource } from "./events";
import { hasValidPageHead } from "./head";
import { type PageProtocol, protocolsMatch, readPageProtocol } from "./protocol";

// --- types ---

export type PageReloadReason =
  | "cross-origin"
  | "status"
  | "content-type"
  | "content-disposition"
  | "invalid-html"
  | "protocol";

export interface FetchedPage {
  readonly requestedUrl: URL;
  readonly finalUrl: URL;
  readonly document: Document;
  readonly response: Response;
  readonly deliverySource: PageNavigationDeliverySource;
}

export type PageLoadResult =
  | {
      readonly kind: "swap";
      readonly page: FetchedPage;
    }
  | {
      readonly kind: "reload";
      readonly url: URL;
      readonly reason: PageReloadReason;
    };

export interface FetchPageOptions {
  readonly signal: AbortSignal;
  readonly expectedOrigin: string;
  readonly currentProtocol: PageProtocol;
  readonly fetchImpl?: typeof fetch;
  readonly parseHtml?: (html: string) => Document;
}

export class PageLoadError extends Error {
  readonly phase: "request" | "validation";

  constructor(phase: "request" | "validation", cause: unknown) {
    super(phase === "request" ? "Failed to fetch page" : "Failed to parse page", { cause });

    this.name = "PageLoadError";
    this.phase = phase;
  }
}

// --- helper method ---

function reload(url: URL, reason: PageReloadReason): PageLoadResult {
  return {
    kind: "reload",
    url: new URL(url),
    reason,
  };
}

function isAbortError(error: unknown, signal: AbortSignal): boolean {
  return signal.aborted || (error instanceof DOMException && error.name === "AbortError");
}

function deliverSource(response: Response): PageNavigationDeliverySource {
  if (response.headers.has("X-Service-Worker-Cache")) {
    return "service-worker";
  }
  if (response.headers.has("CF-Cache-Status")) {
    return "cloudflare";
  }
  return "origin";
}

// --- core method ---

export async function page(requestedUrl: URL, options: FetchPageOptions): Promise<PageLoadResult> {
  const navigationUrl = new URL(requestedUrl);
  // cross-origin, reload page
  if (
    !["http:", "https:"].includes(navigationUrl.protocol) ||
    navigationUrl.origin !== options.expectedOrigin
  ) {
    return reload(navigationUrl, "cross-origin");
  }

  const requestUrl = new URL(navigationUrl);
  requestUrl.hash = "";

  // request
  let response: Response;
  try {
    response = await (options.fetchImpl ?? fetch)(requestUrl, {
      method: "GET",
      credentials: "same-origin",
      redirect: "follow",
      headers: {
        Accept: "text/html",
      },
      signal: options.signal,
    });
    options.signal.throwIfAborted();
  } catch (e) {
    if (isAbortError(e, options.signal)) {
      throw e;
    }

    throw new PageLoadError("request", e);
  }

  const finalUrl = response.url ? new URL(response.url, requestUrl) : new URL(requestUrl);
  if (finalUrl.origin !== options.expectedOrigin) {
    // cross-origin, reload page
    return reload(navigationUrl, "cross-origin");
  }

  // recover hash
  finalUrl.hash = navigationUrl.hash;

  if (!response.ok || response.status !== 200) {
    return reload(finalUrl, "status");
  }

  // check content type (except html)
  const contentType = response.headers.get("Content-Type")?.split(";", 1)[0].trim().toLowerCase();
  if (contentType !== "text/html") {
    return reload(finalUrl, "content-type");
  }

  // RFC 6266
  //  Content-Disposition: inline                             - normal page
  //  Content-Disposition: attachment; filename="report.pdf"  - download attachment
  const contentDisposition =
    response.headers.get("Content-Disposition")?.split(";", 1)[0].trim().toLowerCase() ?? "";
  if (contentDisposition === "attachment") {
    return reload(finalUrl, "content-disposition");
  }

  // receive request body
  let html: string;
  try {
    html = await response.text();
    options.signal.throwIfAborted();
  } catch (e) {
    if (isAbortError(e, options.signal)) {
      throw e;
    }

    throw new PageLoadError("request", e);
  }

  // parse HTML
  let parsed: Document;
  try {
    parsed = options.parseHtml?.(html) ?? new DOMParser().parseFromString(html, "text/html");
    options.signal.throwIfAborted();
  } catch (e) {
    if (isAbortError(e, options.signal)) {
      throw e;
    }

    throw new PageLoadError("validation", e);
  }
  if (!hasValidPageHead(parsed)) {
    return reload(finalUrl, "invalid-html");
  }
  if (!protocolsMatch(options.currentProtocol, readPageProtocol(parsed))) {
    return reload(finalUrl, "protocol");
  }

  return {
    kind: "swap",
    page: {
      requestedUrl: navigationUrl,
      finalUrl,
      document: parsed,
      response,
      deliverySource: deliverSource(response),
    },
  };
}
