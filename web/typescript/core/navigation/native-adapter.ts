// it uses a very very very new API (in 2026) - Navigation API
// docs: https://developer.mozilla.org/docs/Web/API/Navigation_API

import { PAGE_TRANSITION_TIMING, setupPageTransition } from "../page-transition";
import {
  APP_PAGE_EVENT,
  emitPageEvent,
  type PageNavigationDeliverySource,
  type PageNavigationDetail,
  type PageNavigationOutcome,
  type PageNavigationPhase,
  type PageNavigationType,
  type PageSwapDetail,
} from "./events";
import { preparePageHead } from "./head";
import { page, PageLoadError, type PageLoadResult } from "./page";
import { readPageProtocol } from "./protocol";
import { isPageNavigationUrl, shouldInterceptNavigation } from "./route-policy";

type TransactionStage = "loading" | "swapping" | "settling" | "finished";

interface NavigationTransaction {
  id: number;
  from: URL;
  requestedUrl: URL;
  finalUrl?: URL;
  navigationType: PageNavigationType;
  deliverySource?: PageNavigationDeliverySource;
  stage: TransactionStage;
  controller: AbortController;
}

interface NativePageNavigationOptions {
  loadPage?: typeof page;
  prepareHead?: typeof preparePageHead;
  navigate?: (url: URL) => void;
  reload?: () => void;
  wait?: (duration: number, signal: AbortSignal) => Promise<void>;
  prefersReducedMotion?: () => boolean;
}

function waitFor(duration: number, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      signal.removeEventListener("abort", aborted);
      resolve();
    }, duration);

    const aborted = () => {
      clearTimeout(timeout);
      reject(signal.reason);
    };
    signal.addEventListener("abort", aborted, { once: true });
  });
}

export function setupNativePageNavigation(
  document: Document,
  options: NativePageNavigationOptions = {},
) {
  const view = document.defaultView;
  if (!view) {
    return () => undefined;
  }

  const currentProtocol = readPageProtocol(document);
  if (!currentProtocol) {
    // let browser reflush the page
    return () => undefined;
  }

  let fullNavigationPending = false;
  let nextNavigationId = 0;
  let currentUrl = new URL(view.location.href);
  let activeTransaction: NavigationTransaction | undefined;
  const controller = new AbortController();
  const loadPage = options.loadPage ?? page;
  const prepareHead = options.prepareHead ?? preparePageHead;
  const navigate = options.navigate ?? ((url: URL) => view.location.assign(url.href));
  const reload = options.reload ?? (() => view.location.reload());
  const wait = options.wait ?? waitFor;
  const prefersReducedMotion =
    options.prefersReducedMotion ??
    ((): boolean => view.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);

  const isCurrent = (transaction: NavigationTransaction): boolean =>
    activeTransaction === transaction &&
    transaction.stage !== "finished" &&
    !fullNavigationPending &&
    !controller.signal.aborted;

  const detailFor = (t: NavigationTransaction): PageNavigationDetail => ({
    navigationId: t.id,
    root: document.body,
    from: new URL(t.from),
    requestedUrl: new URL(t.requestedUrl),
    navigationType: t.navigationType,
    source: "fetch",
    ...(t.finalUrl ? { finalUrl: new URL(t.finalUrl) } : {}),
    ...(t.deliverySource ? { deliverySource: t.deliverySource } : {}),
  });

  const swapDetailFor = (t: NavigationTransaction): PageSwapDetail => ({
    navigationId: t.id,
    root: document.body,
  });

  const finish = (t: NavigationTransaction, outcome: PageNavigationOutcome) => {
    if (t.stage === "finished") {
      return;
    }

    t.stage = "finished";
    if (activeTransaction === t) {
      activeTransaction = undefined;
      document.body.removeAttribute("aria-busy");
    }
    if (outcome === "completed") {
      currentUrl = new URL(t.finalUrl ?? t.requestedUrl);
    }

    emitPageEvent(document, APP_PAGE_EVENT.navigationEnd, { ...detailFor(t), outcome });
  };

  const fail = (t: NavigationTransaction, phase: PageNavigationPhase, error: unknown) => {
    if (t.stage === "finished") {
      return;
    }

    t.stage = "finished";
    if (activeTransaction === t) {
      activeTransaction = undefined;
      document.body.removeAttribute("aria-busy");
    }
    emitPageEvent(document, APP_PAGE_EVENT.navigationError, { ...detailFor(t), phase, error });
  };

  const cancel = (t: NavigationTransaction) => {
    if (t.stage === "finished") {
      return;
    }

    const restorePage = t.stage === "swapping";
    t.controller.abort(new DOMException("Navigation cancelled", "AbortError"));
    if (restorePage) {
      emitPageEvent(document, APP_PAGE_EVENT.afterSwap, swapDetailFor(t));
    }
    finish(t, "cancelled");
  };

  const fallbackTo = (t: NavigationTransaction, url: URL) => {
    fullNavigationPending = true;
    t.controller.abort(new DOMException("Falling back to full navigation", "AbortError"));
    finish(t, "fallback");
    navigate(url);
  };

  const reloadAfterError = (
    t: NavigationTransaction,
    url: URL,
    phase: PageNavigationPhase,
    error: unknown,
  ): void => {
    fullNavigationPending = true;
    t.controller.abort(error);
    fail(t, phase, error);
    navigate(url);
  };

  const swapBodyChildren = (target: HTMLElement, source: HTMLElement) => {
    const nodes = Array.from(source.childNodes).map((node) => document.importNode(node, true));
    target.replaceChildren(...nodes);
  };

  const handleNavigate = (event: NavigateEvent) => {
    if (fullNavigationPending) {
      return;
    }

    if (!shouldInterceptNavigation(event, currentUrl)) {
      const destination = new URL(event.destination.url);
      if (
        event.canIntercept &&
        !event.defaultPrevented &&
        !event.hashChange &&
        event.navigationType === "traverse" &&
        !isPageNavigationUrl(destination, currentUrl.origin)
      ) {
        if (activeTransaction) {
          cancel(activeTransaction);
        }
        try {
          event.intercept({
            handler() {
              reload();
            },
          });
          fullNavigationPending = true;
        } catch {
          return;
        }
      }
      return;
    }

    if (
      activeTransaction &&
      activeTransaction.stage !== "loading" &&
      activeTransaction.stage !== "finished"
    ) {
      cancel(activeTransaction);
      return;
    }
    if (activeTransaction) {
      cancel(activeTransaction);
    }

    const transaction: NavigationTransaction = {
      id: ++nextNavigationId,
      from: new URL(currentUrl),
      requestedUrl: new URL(event.destination.url),
      navigationType: event.navigationType as "push" | "replace" | "traverse",
      stage: "loading",
      controller: new AbortController(),
    };

    try {
      event.intercept({
        focusReset: "after-transition",
        scroll: "after-transition",
        async handler() {
          const signal = AbortSignal.any([
            event.signal,
            controller.signal,
            transaction.controller.signal,
          ]);
          let result: PageLoadResult;
          try {
            result = await loadPage(transaction.requestedUrl, {
              signal,
              expectedOrigin: view.location.origin,
              currentProtocol,
            });
          } catch (e) {
            if (!isCurrent(transaction)) {
              return;
            }
            if (signal.aborted) {
              cancel(transaction);
              return;
            }
            reloadAfterError(
              transaction,
              transaction.requestedUrl,
              e instanceof PageLoadError ? e.phase : "request",
              e,
            );
            return;
          }

          if (!isCurrent(transaction)) {
            return;
          }
          if (result.kind === "reload") {
            fallbackTo(transaction, result.url);
            return;
          }

          transaction.finalUrl = new URL(result.page.finalUrl);
          transaction.deliverySource = result.page.deliverySource;
          if (transaction.finalUrl.href !== transaction.requestedUrl.href) {
            fallbackTo(transaction, transaction.finalUrl);
            return;
          }

          let head: Awaited<ReturnType<typeof preparePageHead>> | undefined;
          try {
            head = await prepareHead(document, result.page.document, {
              signal,
              currentUrl,
              nextUrl: transaction.finalUrl,
            });

            if (!isCurrent(transaction)) {
              head.rollback();
              return;
            }

            transaction.stage = "swapping";
            emitPageEvent(document, APP_PAGE_EVENT.beforeSwap, swapDetailFor(transaction));
            if (!prefersReducedMotion()) {
              await wait(PAGE_TRANSITION_TIMING.swapDelay, signal);
            }
            signal.throwIfAborted();
            if (!isCurrent(transaction)) {
              head.rollback();
              return;
            }

            head.commit();
            swapBodyChildren(document.body, result.page.document.body);
            transaction.stage = "settling";
            emitPageEvent(document, APP_PAGE_EVENT.afterSwap, swapDetailFor(transaction));
            if (!prefersReducedMotion()) {
              await wait(PAGE_TRANSITION_TIMING.settleDelay, signal);
            }
            signal.throwIfAborted();
            if (!isCurrent(transaction)) {
              return;
            }

            finish(transaction, "completed");
          } catch (e) {
            head?.rollback();
            if (!isCurrent(transaction)) {
              return;
            }
            if (signal.aborted) {
              cancel(transaction);
              return;
            }
            reloadAfterError(transaction, transaction.requestedUrl, "swap", e);
          }
        },
      });
    } catch {
      transaction.controller.abort();
      return;
    }

    activeTransaction = transaction;
    document.body.setAttribute("aria-busy", "true");
    emitPageEvent(document, APP_PAGE_EVENT.navigationStart, detailFor(transaction));
  };

  view.navigation.addEventListener("navigate", handleNavigate, {
    signal: controller.signal,
  });

  const stopPageTransition = setupPageTransition(document);

  return () => {
    if (activeTransaction) {
      cancel(activeTransaction);
    }
    controller.abort();
    stopPageTransition();
  };
}
