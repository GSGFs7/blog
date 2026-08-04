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
      const { setupNativePageNavigation } = await import("./native-adapter");
      setupNativePageNavigation(document);
    } else {
      await import("../htmx");
    }
  }

  // native mode
  if (requestedMode === "native" && hasNavigationAPI()) {
    const { setupNativePageNavigation } = await import("./native-adapter");
    setupNativePageNavigation(document);
  }

  // htmx mode
  if (requestedMode === "htmx") {
    await import("../htmx");
  }

  // no navigation
}
