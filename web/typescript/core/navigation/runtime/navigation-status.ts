import { APP_PAGE_EVENT } from "../contracts";

const LOADING_DELAY_MS = 150;

export function setupNavigationStatus(document: Document): () => void {
  const controller = new AbortController();
  let activeNavigationId: number | undefined;
  let showTimer: ReturnType<typeof setTimeout> | undefined;

  const cancelTimer = () => {
    clearTimeout(showTimer);
    showTimer = undefined;
  };

  const clear = () => {
    cancelTimer();
    activeNavigationId = undefined;
    document.documentElement.removeAttribute("data-navigation-loading");
  };

  const finish = (
    event: DocumentEventMap["app:navigation-end"] | DocumentEventMap["app:navigation-error"],
  ) => {
    if (event.detail.navigationId === activeNavigationId) {
      clear();
    }
  };

  document.addEventListener(
    APP_PAGE_EVENT.navigationStart,
    (event) => {
      if (event.detail.reason === "revalidation") {
        return;
      }

      activeNavigationId = event.detail.navigationId;
      cancelTimer();
      if (!document.documentElement.hasAttribute("data-navigation-loading")) {
        showTimer = setTimeout(() => {
          showTimer = undefined;
          document.documentElement.setAttribute("data-navigation-loading", "");
        }, LOADING_DELAY_MS);
      }
    },
    { signal: controller.signal },
  );
  document.addEventListener(APP_PAGE_EVENT.navigationEnd, finish, { signal: controller.signal });
  document.addEventListener(APP_PAGE_EVENT.navigationError, finish, { signal: controller.signal });

  return () => {
    controller.abort();
    clear();
  };
}
