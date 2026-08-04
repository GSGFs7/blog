const hasNavigationAPI = () =>
  "navigation" in window &&
  "NavigateEvent" in window &&
  typeof NavigateEvent.prototype.intercept === "function";

const getNavigationConfig = () =>
  document.querySelector<HTMLMetaElement>('meta[name="page-navigation-mode"]')?.content ?? "auto";

export async function setupNavigation() {
  const requestedMode = getNavigationConfig();

  // auto mode
  if (requestedMode === "auto") {
    if (hasNavigationAPI()) {
      const { setupNativePageNavigation } = await import("./adapters/native");
      setupNativePageNavigation(document);
    } else {
      await import("./adapters/htmx/bootstrap");
    }
  }

  // native mode
  if (requestedMode === "native" && hasNavigationAPI()) {
    const { setupNativePageNavigation } = await import("./adapters/native");
    setupNativePageNavigation(document);
  }

  // htmx mode
  if (requestedMode === "htmx") {
    await import("./adapters/htmx/bootstrap");
  }

  // no navigator
}
