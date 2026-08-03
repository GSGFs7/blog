const RELOAD_PREFIXES = ["/account/", "/api/", "/not-admin/", "/prometheus/"];
const RELOAD_PATHS = new Set([
  "/blog/feed.atom",
  "/blog/latest",
  "/blog/random",
  "/favicon.ico",
  "/llms.txt",
  "/login",
  "/robots.txt",
  "/sitemap.xml",
  "/test",
  "/user",
]);

function normalizedPathname(pathname: string): string {
  if (pathname === "/") {
    return pathname;
  }

  return pathname.replace(/\/+$/, "");
}

export function isPageNavigationUrl(url: URL, origin: string): boolean {
  if ((url.protocol !== "http:" && url.protocol !== "https:") || url.origin !== origin) {
    return false;
  }

  const pathname = normalizedPathname(url.pathname);
  if (RELOAD_PATHS.has(pathname) || RELOAD_PREFIXES.some((p) => pathname.startsWith(p))) {
    return false;
  }

  return !(
    /^\/blog\/\d+$/.test(pathname) || // post id
    pathname.endsWith(".atom") ||
    pathname.endsWith(".md")
  );
}

export function isPageNavigationSource(source: Element | null): boolean {
  if (!source) {
    return true;
  }

  // if mark as navigation disabled
  if (
    source.closest(
      "[data-nav-ignore], [data-nav-reload], [contenteditable]:not([contenteditable='false'])",
    )
  ) {
    return false;
  }

  // not intercept form
  if (source.closest("form")) {
    return false;
  }

  const anchor = source.closest("a, area");
  if (!anchor || !anchor.hasAttribute("download")) {
    return true;
  }

  const target = anchor.getAttribute("target")?.trim().toLowerCase();
  if (target && target !== "_self") {
    return false;
  }

  const rel = anchor.getAttribute("rel")?.toLowerCase().split(/\s+/) ?? [];
  if (rel.includes("external")) {
    return false;
  }

  return true;
}

export function shouldInterceptNavigation(event: NavigateEvent, currentUrl: URL): boolean {
  return (
    event.canIntercept &&
    !event.defaultPrevented &&
    !event.hashChange &&
    event.downloadRequest === null &&
    event.formData === null &&
    event.navigationType !== "reload" &&
    isPageNavigationSource(event.sourceElement) &&
    isPageNavigationUrl(new URL(event.destination.url), currentUrl.origin)
  );
}
