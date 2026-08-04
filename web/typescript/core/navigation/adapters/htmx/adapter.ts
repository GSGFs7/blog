import htmx, { type HtmxBeforeSwapDetails, type HtmxResponseInfo } from "htmx.org";

import {
  APP_PAGE_EVENT,
  emitPageEvent,
  type PageNavigationOutcome,
  type PageNavigationPhase,
  type PageNavigationSource,
  type PageNavigationType,
  type PageNavigationDetail,
  type PageSwapDetail,
} from "../../contracts";
import {
  type PageProtocol,
  parsePageProtocol,
  protocolsMatch,
  readPageProtocol,
} from "../../contracts";
import { PAGE_TRANSITION_TIMING } from "../../runtime";

const EXTENSION_NAME = "app-page-lifecycle";
export const HTMX_PAGE_TRANSITION_SWAP =
  `innerHTML swap:${PAGE_TRANSITION_TIMING.swapDelay}ms ` +
  `settle:${PAGE_TRANSITION_TIMING.settleDelay}ms`;

type TransactionStage = "loading" | "swapping" | "settling" | "finished";

interface NavigationTransaction {
  id: number;
  from: URL;
  requestedUrl: URL;
  finalUrl?: URL;
  navigationType: PageNavigationType;
  source: PageNavigationSource;
  stage: TransactionStage;
  xhr?: XMLHttpRequest;
}

interface HtmxHistorySwapDetails {
  historyElt: Element;
  swapSpec: {
    swapDelay: number;
    settleDelay: number;
  };
}

interface HtmxHistoryDetail extends HtmxHistorySwapDetails {
  path: string;
  xhr?: XMLHttpRequest;
}

interface HtmxPageLifecycleOptions {
  navigate?: (url: URL) => void;
  currentProtocol?: PageProtocol | null;
}

const ERROR_PHASES: Partial<Record<string, PageNavigationPhase>> = {
  "htmx:responseError": "request",
  "htmx:sendError": "request",
  "htmx:timeout": "request",
  "htmx:onLoadError": "validation",
  "htmx:swapError": "swap",
  "htmx:historyCacheMissLoadError": "request",
};

// toooo complex
export function setupHtmxPageLifecycle(
  document: Document,
  options: HtmxPageLifecycleOptions = {},
): () => void {
  const view = document.defaultView;
  if (!view) {
    return () => undefined;
  }

  const currentProtocol =
    options.currentProtocol === undefined ? readPageProtocol(document) : options.currentProtocol;

  const navigate = options.navigate ?? ((url: URL) => view.location.assign(url.href));
  const prefersReducedMotion = (): boolean =>
    view.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  const historyGuardController = new AbortController();
  let nextNavigationId = 0;
  let currentUrl = new URL(view.location.href);
  let activeTransaction: NavigationTransaction | undefined = undefined;
  let historyTransaction: NavigationTransaction | undefined = undefined;
  let swapTransaction: NavigationTransaction | undefined = undefined;
  const transactions = new WeakMap<XMLHttpRequest, NavigationTransaction>();

  const toUrl = (value: string): URL => new URL(value, view.location.href);

  const inheritedAttribute = (element: Element, name: string): string | null => {
    let current: Element | null = element;
    while (current) {
      const value = current.getAttribute(name) ?? current.getAttribute(`data-${name}`);
      if (value !== null) {
        return value;
      }
      current = current.parentElement;
    }
    return null;
  };

  const navigationTypeFor = (detail: HtmxResponseInfo): PageNavigationType => {
    const replace =
      detail.etc.replace ?? inheritedAttribute(detail.requestConfig.elt, "hx-replace-url");
    return replace !== undefined && replace !== null && replace !== "false" ? "replace" : "push";
  };

  const applyResponseNavigation = (
    transaction: NavigationTransaction,
    detail: HtmxBeforeSwapDetails,
  ) => {
    const replaceUrl = detail.xhr.getResponseHeader("HX-Replace-Url");
    const pushUrl = detail.xhr.getResponseHeader("HX-Push-Url");
    if (replaceUrl && replaceUrl !== "false") {
      transaction.navigationType = "replace";
    } else if (pushUrl && pushUrl !== "false") {
      transaction.navigationType = "push";
    }

    const explicitUrl = replaceUrl ?? pushUrl;
    if (explicitUrl && explicitUrl !== "true" && explicitUrl !== "false") {
      transaction.finalUrl = toUrl(explicitUrl);
      return;
    }

    transaction.finalUrl = toUrl(detail.pathInfo.responsePath ?? detail.pathInfo.finalRequestPath);
  };

  const guardHistoryResponse = (xhr: XMLHttpRequest, transaction: NavigationTransaction): void => {
    xhr.addEventListener(
      "load",
      (event) => {
        if (transaction.stage !== "loading") {
          return;
        }

        if (xhr.status < 200 || xhr.status >= 400) {
          return;
        }

        const responseProtocol = parsePageProtocol(xhr.responseText);
        if (protocolsMatch(currentProtocol, responseProtocol)) {
          return;
        }

        event.stopImmediatePropagation();

        const finalUrl = xhr.responseURL ? toUrl(xhr.responseURL) : transaction.requestedUrl;
        fallbackTransaction(transaction, finalUrl);
      },
      {
        capture: true,
        once: true,
        signal: historyGuardController.signal,
      },
    );
  };

  const detailFor = (transaction: NavigationTransaction): PageNavigationDetail => ({
    navigationId: transaction.id,
    root: document.body,
    from: new URL(transaction.from),
    requestedUrl: new URL(transaction.requestedUrl),
    navigationType: transaction.navigationType,
    source: transaction.source,
    ...(transaction.finalUrl ? { finalUrl: new URL(transaction.finalUrl) } : {}),
  });

  const swapDetailFor = (transaction: NavigationTransaction): PageSwapDetail => ({
    navigationId: transaction.id,
    root: document.body,
  });

  const finish = (transaction: NavigationTransaction, outcome: PageNavigationOutcome) => {
    if (transaction.stage === "finished") {
      return;
    }

    transaction.stage = "finished";
    if (outcome === "completed") {
      currentUrl = new URL(transaction.finalUrl ?? transaction.requestedUrl);
    }

    emitPageEvent(document, APP_PAGE_EVENT.navigationEnd, {
      ...detailFor(transaction),
      outcome,
    });

    if (activeTransaction === transaction) {
      activeTransaction = undefined;
    }
    if (historyTransaction === transaction) {
      historyTransaction = undefined;
    }
    if (swapTransaction === transaction) {
      swapTransaction = undefined;
    }
  };

  const fail = (transaction: NavigationTransaction, phase: PageNavigationPhase, error: unknown) => {
    if (transaction.stage === "finished") {
      return;
    }

    transaction.stage = "finished";
    emitPageEvent(document, APP_PAGE_EVENT.navigationError, {
      ...detailFor(transaction),
      phase,
      error,
    });

    if (activeTransaction === transaction) {
      activeTransaction = undefined;
    }
    if (historyTransaction === transaction) {
      historyTransaction = undefined;
    }
    if (swapTransaction === transaction) {
      swapTransaction = undefined;
    }
  };

  const cancelLoading = (transaction: NavigationTransaction) => {
    if (transaction.stage !== "loading") {
      return;
    }

    const xhr = transaction.xhr;
    finish(transaction, "cancelled");
    if (xhr && xhr.readyState !== view.XMLHttpRequest.DONE) {
      xhr.abort();
    }
  };

  const start = (
    requestedUrl: URL,
    navigationType: PageNavigationType,
    source: PageNavigationSource,
  ): NavigationTransaction => {
    if (activeTransaction?.stage === "loading") {
      cancelLoading(activeTransaction);
    }

    const transaction: NavigationTransaction = {
      id: ++nextNavigationId,
      from: new URL(currentUrl),
      requestedUrl: new URL(requestedUrl),
      navigationType,
      source,
      stage: "loading",
    };

    activeTransaction = transaction;
    emitPageEvent(document, APP_PAGE_EVENT.navigationStart, detailFor(transaction));
    return transaction;
  };

  const fallback = (
    requestedUrl: URL,
    navigationType: PageNavigationType,
    source: PageNavigationSource,
  ): false => {
    const transaction = start(requestedUrl, navigationType, source);
    finish(transaction, "fallback");
    navigate(requestedUrl);
    return false;
  };

  const fallbackTransaction = (transaction: NavigationTransaction, url: URL): false => {
    transaction.finalUrl = url;
    finish(transaction, "fallback");
    navigate(url);
    return false;
  };

  const transactionFrom = (event: CustomEvent): NavigationTransaction | undefined => {
    const xhr = (event.detail as { xhr?: unknown })?.xhr;
    if (xhr instanceof view.XMLHttpRequest) {
      return transactions.get(xhr);
    }

    return event.target === document.body ? historyTransaction : undefined;
  };

  htmx.defineExtension(EXTENSION_NAME, {
    onEvent(name, event) {
      const customEvent = event as CustomEvent;

      if (name === "htmx:beforeRequest") {
        const detail = customEvent.detail as HtmxResponseInfo;
        if (!detail.boosted || detail.target !== document.body) {
          return true;
        }

        const requestedUrl = toUrl(detail.pathInfo.finalRequestPath);
        if (swapTransaction && swapTransaction.stage !== "finished") {
          return fallback(requestedUrl, navigationTypeFor(detail), "fetch");
        }

        const transaction = start(requestedUrl, navigationTypeFor(detail), "fetch");
        transaction.xhr = detail.xhr;
        transactions.set(detail.xhr, transaction);
        return true;
      }

      if (name === "htmx:beforeSwap") {
        const detail = customEvent.detail as HtmxBeforeSwapDetails;
        const transaction = transactionFrom(customEvent);
        if (transaction?.stage === "finished") {
          detail.shouldSwap = false;
          return true;
        }
        if (
          !transaction ||
          transaction.stage !== "loading" ||
          !detail.boosted ||
          !detail.shouldSwap ||
          detail.target !== document.body
        ) {
          return true;
        }

        applyResponseNavigation(transaction, detail);

        const responseProtocol = parsePageProtocol(detail.serverResponse);
        if (!protocolsMatch(currentProtocol, responseProtocol)) {
          detail.shouldSwap = false;
          customEvent.preventDefault();

          return fallbackTransaction(transaction, transaction.finalUrl ?? transaction.requestedUrl);
        }

        transaction.stage = "swapping";
        swapTransaction = transaction;

        applyHtmxPageTransition(detail, document.body, prefersReducedMotion());
        emitPageEvent(document, APP_PAGE_EVENT.beforeSwap, swapDetailFor(transaction));
        return true;
      }

      if (name === "htmx:historyCacheHit") {
        const detail = customEvent.detail as HtmxHistoryDetail;
        if (detail.historyElt !== document.body) {
          return true;
        }

        const requestedUrl = toUrl(detail.path);
        if (swapTransaction && swapTransaction.stage !== "finished") {
          return fallback(requestedUrl, "traverse", "cache");
        }

        const transaction = start(requestedUrl, "traverse", "cache");
        transaction.finalUrl = requestedUrl;
        transaction.stage = "swapping";
        historyTransaction = transaction;
        swapTransaction = transaction;

        applyHtmxHistoryPageTransition(detail, document.body, prefersReducedMotion());
        emitPageEvent(document, APP_PAGE_EVENT.beforeSwap, swapDetailFor(transaction));
        return true;
      }

      if (name === "htmx:historyCacheMiss") {
        const detail = customEvent.detail as HtmxHistoryDetail;
        if (detail.historyElt !== document.body || !detail.xhr) {
          return true;
        }

        const requestedUrl = toUrl(detail.path);
        if (swapTransaction && swapTransaction.stage !== "finished") {
          return fallback(requestedUrl, "traverse", "fetch");
        }

        const transaction = start(requestedUrl, "traverse", "fetch");
        transaction.xhr = detail.xhr;
        historyTransaction = transaction;
        transactions.set(detail.xhr, transaction);

        guardHistoryResponse(detail.xhr, transaction);
        return true;
      }

      if (name === "htmx:historyCacheMissLoad") {
        const transaction = transactionFrom(customEvent);
        if (!transaction || transaction.stage !== "loading") {
          return true;
        }

        transaction.finalUrl = transaction.xhr?.responseURL
          ? toUrl(transaction.xhr.responseURL)
          : transaction.requestedUrl;
        transaction.stage = "swapping";
        swapTransaction = transaction;
        applyHtmxHistoryPageTransition(
          customEvent.detail as HtmxHistorySwapDetails,
          document.body,
          prefersReducedMotion(),
        );
        emitPageEvent(document, APP_PAGE_EVENT.beforeSwap, swapDetailFor(transaction));
        return true;
      }

      if (name === "htmx:afterSwap" && customEvent.target === document.body) {
        const transaction = transactionFrom(customEvent);
        if (!transaction || transaction.stage !== "swapping") {
          return true;
        }

        transaction.stage = "settling";
        emitPageEvent(document, APP_PAGE_EVENT.afterSwap, swapDetailFor(transaction));
        return true;
      }

      if (name === "htmx:afterSettle" && customEvent.target === document.body) {
        const transaction = transactionFrom(customEvent);
        if (transaction?.stage === "settling") {
          finish(transaction, "completed");
        }
        return true;
      }

      if (name === "htmx:sendAbort") {
        const transaction = transactionFrom(customEvent);
        if (transaction) {
          finish(transaction, "cancelled");
        }
        return true;
      }

      if (name === "htmx:afterRequest") {
        if ((customEvent.detail as { error?: unknown }).error) {
          return true;
        }

        const transaction = transactionFrom(customEvent);
        if (transaction?.stage === "loading") {
          finish(transaction, "cancelled");
        }
        return true;
      }

      const errorPhase = ERROR_PHASES[name];
      const transaction = transactionFrom(customEvent);
      if (errorPhase && transaction) {
        fail(
          transaction,
          errorPhase,
          (customEvent.detail as { error?: unknown }).error ?? new Error(name),
        );
      }
      return true;
    },
  });

  return () => {
    historyGuardController.abort();
    htmx.removeExtension(EXTENSION_NAME);
    if (activeTransaction && activeTransaction.stage !== "finished") {
      finish(activeTransaction, "cancelled");
    }
  };
}

export function applyHtmxPageTransition(
  detail: HtmxBeforeSwapDetails,
  body: HTMLElement,
  reducedMotion: boolean,
): void {
  if (
    !detail.boosted ||
    !detail.shouldSwap ||
    detail.target !== body ||
    reducedMotion ||
    detail.swapOverride != null
  ) {
    return;
  }

  detail.swapOverride = HTMX_PAGE_TRANSITION_SWAP;
}

export function applyHtmxHistoryPageTransition(
  detail: HtmxHistorySwapDetails,
  body: HTMLElement,
  reducedMotion: boolean,
): void {
  if (detail.historyElt !== body || reducedMotion) {
    return;
  }

  detail.swapSpec.swapDelay = PAGE_TRANSITION_TIMING.swapDelay;
  detail.swapSpec.settleDelay = PAGE_TRANSITION_TIMING.settleDelay;
}
