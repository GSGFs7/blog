// it uses a very very very new API (in 2026) - Navigation API
// docs: https://developer.mozilla.org/docs/Web/API/Navigation_API


import { setupPageTransition } from "../page-transition";
import { readPageProtocol } from "./protocol";

function shouldIntercept(event: NavigateEvent, view: Window): boolean {
  if (!event.canIntercept) {
    return false;
  }
  // not intercept reload
  if (event.navigationType === "reload") {
    return false;
  }
  if (event.hashChange) {
    return false;
  }
  if (event.downloadRequest !== null) {
    return false;
  }
  if (event.formData !== null) {
    return false;
  }

  // if request url not match
  const destination = new URL(event.destination.url);
  if (destination.origin !== view.location.origin) {
    return false;
  }

  return true;
}

export function setupNativePageNavigation(document: Document) {
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
  const controller = new AbortController();
  const handleNavigate = (event: NavigateEvent) => {
    if (fullNavigationPending || !shouldIntercept(event, view)) {
      return;
    }

    // TODO
  };
  view.navigation.addEventListener("navigate", handleNavigate, {
    signal: controller.signal,
  });

  const stopPageTransition = setupPageTransition(document);

  return () => {
    controller.abort();
    stopPageTransition();
  };
}
