// it uses a very very very new API (in 2026) - Navigation API
// docs: https://developer.mozilla.org/docs/Web/API/Navigation_API

import {
  APP_PAGE_EVENT,
  emitPageEvent,
  type PageNavigationDeliverySource,
  type PageNavigationDetail,
  type PageNavigationOutcome,
  type PageNavigationPhase,
  type PageNavigationType,
  type PageSwapDetail,
} from "../../contracts";
import { readPageProtocol } from "../../contracts";
import { isPageNavigationUrl, shouldInterceptNavigation } from "../../policy";
import { PAGE_TRANSITION_TIMING, setupPageTransition } from "../../runtime";
import { preparePreservation } from "../../runtime/preservation";
import { setupBackgroundUpdateGuard } from "./background-update";
import { preparePageHead } from "./head";
import { type FetchedPage, page, PageLoadError, type PageLoadResult } from "./page";
import { setupNativePrefetch } from "./prefetch";

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
  preservedRoots: readonly HTMLElement[];
  revalidate: boolean;
}

interface NativePageNavigationOptions {
  loadPage?: typeof page;
  prepareHead?: typeof preparePageHead;
  navigate?: (url: URL) => void;
  reload?: () => void;
  wait?: (duration: number, signal: AbortSignal) => Promise<void>;
  prefersReducedMotion?: () => boolean;
  supportsPrecommitRedirect?: () => boolean;
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

  const originalScrollRestoration = view.history.scrollRestoration;
  const restoreScrollRestoration = () => {
    view.history.scrollRestoration = originalScrollRestoration;
  };

  let fullNavigationPending = false;
  let nextNavigationId = 0;
  let currentUrl = new URL(view.location.href);
  let activeTransaction: NavigationTransaction | undefined;
  let displayRevision = 0;
  const controller = new AbortController();
  const loadPage = options.loadPage ?? page;
  const prepareHead = options.prepareHead ?? preparePageHead;
  const navigate = options.navigate ?? ((url: URL) => view.location.assign(url.href));
  const reload = options.reload ?? (() => view.location.reload());
  const wait = options.wait ?? waitFor;
  const prefersReducedMotion =
    options.prefersReducedMotion ??
    ((): boolean => view.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  const supportsPrecommitRedirect =
    options.supportsPrecommitRedirect ??
    (() => {
      const PrecommitController = view.NavigationPrecommitController;
      return (
        typeof PrecommitController === "function" &&
        typeof PrecommitController.prototype.redirect === "function" &&
        typeof PrecommitController.prototype.addHandler === "function"
      );
    });

  const isCurrent = (transaction: NavigationTransaction): boolean =>
    activeTransaction === transaction &&
    transaction.stage !== "finished" &&
    !fullNavigationPending &&
    !controller.signal.aborted;

  const detailFor = (t: NavigationTransaction): PageNavigationDetail => ({
    navigationId: t.id,
    root: document.body,
    preservedRoots: t.preservedRoots,
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
    preservedRoots: t.preservedRoots,
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

    t.controller.abort(new DOMException("Navigation cancelled", "AbortError"));
    finish(t, "cancelled");
  };

  const fallbackTo = (t: NavigationTransaction, url: URL) => {
    fullNavigationPending = true;
    t.controller.abort(new DOMException("Falling back to full navigation", "AbortError"));
    finish(t, "fallback");
    restoreScrollRestoration();
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
    restoreScrollRestoration();
    navigate(url);
  };

  const loadTransaction = async (
    transaction: NavigationTransaction,
    signal: AbortSignal,
  ): Promise<FetchedPage | undefined> => {
    let result: PageLoadResult;
    try {
      const prefetched = await prefetch.take(transaction.requestedUrl, signal);
      transaction.revalidate = prefetched?.stale ?? false;
      result = prefetched
        ? { kind: "swap", page: prefetched.page }
        : await loadPage(transaction.requestedUrl, {
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
    if (!isPageNavigationUrl(transaction.finalUrl, currentUrl.origin)) {
      fallbackTo(transaction, transaction.finalUrl);
      return;
    }

    return result.page;
  };

  const prepareBodySwap = (fetchedPage: FetchedPage) => {
    const incomingBody = document.importNode(fetchedPage.document.body, true);
    const plan = preparePreservation(document.body, incomingBody);

    return {
      preservedRoots: plan.roots,
      commit(
        head: Awaited<ReturnType<typeof prepareHead>>,
        detail: PageSwapDetail,
        scroll?: () => void,
      ) {
        const minHeight = document.body.style.getPropertyValue("min-height");
        const priority = document.body.style.getPropertyPriority("min-height");
        document.body.style.setProperty("min-height", `${document.documentElement.scrollHeight}px`);

        try {
          head.commit();
          emitPageEvent(document, APP_PAGE_EVENT.beforeSwap, detail);

          for (const { current, incoming } of plan.pairs) {
            incoming.replaceWith(current);
          }

          document.body.replaceChildren(...Array.from(incomingBody.childNodes));
          scroll?.();
        } finally {
          if (minHeight) {
            document.body.style.setProperty("min-height", minHeight, priority);
          } else {
            document.body.style.removeProperty("min-height");
          }
        }
      },
    };
  };

  const swapTransaction = async (
    transaction: NavigationTransaction,
    fetchedPage: FetchedPage,
    signal: AbortSignal,
    scroll: () => void,
  ): Promise<void> => {
    if (!isCurrent(transaction)) {
      return;
    }

    // only the latest version
    const revision = displayRevision;
    let head: Awaited<ReturnType<typeof preparePageHead>> | undefined;

    try {
      head = await prepareHead(document, fetchedPage.document, {
        signal,
        currentUrl,
        nextUrl: transaction.finalUrl!,
      });

      if (!isCurrent(transaction)) {
        head.rollback();
        return;
      }

      transaction.stage = "swapping";
      emitPageEvent(document, APP_PAGE_EVENT.beforeLeave, swapDetailFor(transaction));
      if (!prefersReducedMotion()) {
        await wait(PAGE_TRANSITION_TIMING.swapDelay, signal);
      }
      signal.throwIfAborted();
      if (!isCurrent(transaction)) {
        head.rollback();
        return;
      }

      const swap = prepareBodySwap(fetchedPage);
      transaction.preservedRoots = swap.preservedRoots;

      swap.commit(head, swapDetailFor(transaction), scroll);

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

      if (transaction.revalidate) {
        void revalidateDisplayedPage(fetchedPage, revision, transaction.id);
      }
    } catch (e) {
      head?.rollback();
      if (!isCurrent(transaction)) {
        return;
      }
      if (signal.aborted) {
        cancel(transaction);
        return;
      }
      reloadAfterError(transaction, transaction.finalUrl ?? transaction.requestedUrl, "swap", e);
    }
  };

  const handleNavigate = (event: NavigateEvent) => {
    displayRevision++;

    if (fullNavigationPending) {
      restoreScrollRestoration();
      return;
    }

    if (!shouldInterceptNavigation(event, currentUrl)) {
      restoreScrollRestoration();
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
      restoreScrollRestoration();
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
      preservedRoots: [],
      revalidate: false,
    };

    const signal = AbortSignal.any([
      event.signal,
      controller.signal,
      transaction.controller.signal,
    ]);

    try {
      view.history.scrollRestoration = "manual";
      const canRedirectBeforeCommit =
        event.cancelable &&
        (event.navigationType === "push" || event.navigationType === "replace") &&
        supportsPrecommitRedirect();

      if (canRedirectBeforeCommit) {
        event.intercept({
          focusReset: "after-transition",
          scroll: "after-transition",
          async precommitHandler(precommit) {
            const fetchedPage = await loadTransaction(transaction, signal);
            if (!fetchedPage) {
              throw signal.reason ?? new DOMException("Navigation did not load", "AbortError");
            }

            if (transaction.finalUrl!.href !== transaction.requestedUrl.href) {
              try {
                precommit.redirect(transaction.finalUrl!);
              } catch {
                fallbackTo(transaction, transaction.finalUrl!);
                throw transaction.controller.signal.reason;
              }
            }

            precommit.addHandler(() =>
              swapTransaction(transaction, fetchedPage, signal, () => event.scroll()),
            );
          },
        });
      } else {
        event.intercept({
          focusReset: "after-transition",
          scroll: "after-transition",
          async handler() {
            const fetchedPage = await loadTransaction(transaction, signal);
            if (!fetchedPage) {
              return;
            }
            if (transaction.finalUrl!.href !== transaction.requestedUrl.href) {
              fallbackTo(transaction, transaction.finalUrl!);
              return;
            }

            await swapTransaction(transaction, fetchedPage, signal, () => event.scroll());
          },
        });
      }
    } catch {
      restoreScrollRestoration();
      transaction.controller.abort();
      return;
    }

    activeTransaction = transaction;
    document.body.setAttribute("aria-busy", "true");
    emitPageEvent(document, APP_PAGE_EVENT.navigationStart, detailFor(transaction));
  };

  const updateDisplayedPage = async (
    fetchedPage: FetchedPage,
    navigationId: number,
    isStillDisplayed: () => boolean,
  ): Promise<void> => {
    if (!isStillDisplayed()) {
      return;
    }

    let head: Awaited<ReturnType<typeof prepareHead>> | undefined;
    try {
      head = await prepareHead(document, fetchedPage.document, {
        signal: controller.signal,
        currentUrl: new URL(view.location.href),
        nextUrl: new URL(view.location.href),
      });

      // user may started aother navigation
      if (!isStillDisplayed()) {
        head.rollback();
        return;
      }

      // prevent update page when entering content
      if (!backgroundUpdateGuard.canApply()) {
        head.rollback();
        return;
      }

      const swap = prepareBodySwap(fetchedPage);
      const detail: PageSwapDetail = {
        navigationId,
        root: document.body,
        preservedRoots: swap.preservedRoots,
        reason: "revalidation",
      };

      swap.commit(head, detail);
      emitPageEvent(document, APP_PAGE_EVENT.afterSwap, detail);
    } catch (e) {
      head?.rollback();
      throw e;
    }
  };

  const revalidateDisplayedPage = async (
    displayedPage: FetchedPage,
    revision: number,
    navigationId: number,
  ) => {
    const isStillDisplayed = () =>
      revision === displayRevision &&
      !controller.signal.aborted &&
      !fullNavigationPending &&
      !activeTransaction;

    if (!isStillDisplayed()) {
      return;
    }

    try {
      const result = await prefetch.refresh(displayedPage.requestedUrl);
      if (!isStillDisplayed() || result.kind !== "swap") {
        return;
      }

      const nextPage = result.page;
      const previousUrl = new URL(displayedPage.finalUrl);
      const nextUrl = new URL(nextPage.finalUrl);
      previousUrl.hash = "";
      nextUrl.hash = "";
      if (previousUrl.href !== nextUrl.href) {
        return;
      }
      if (nextPage.html === displayedPage.html) {
        return;
      }

      await updateDisplayedPage(nextPage, navigationId, isStillDisplayed);
    } catch {}
  };

  view.navigation.addEventListener("navigate", handleNavigate, {
    signal: controller.signal,
  });

  const stopPageTransition = setupPageTransition(document, { prefersReducedMotion });
  const backgroundUpdateGuard = setupBackgroundUpdateGuard(document);
  const prefetch = setupNativePrefetch(document, { loadPage });

  return () => {
    backgroundUpdateGuard.dispose();
    prefetch.dispose();
    if (activeTransaction) {
      cancel(activeTransaction);
    }
    controller.abort();
    restoreScrollRestoration();
    stopPageTransition();
  };
}
