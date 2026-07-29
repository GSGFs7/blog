// navigation protocols
// it makesure navigation correct
// prevent inconsistent behavior between client & server

const NAVIGATION_VERSION_SELECTOR = 'meta[name="app-navigation-version"]';
const BUILD_ID_SELECTOR = 'meta[name="app-build-id"]';

const HISTORY_GENERATION_KEY = "app-navigation-generation";
const HTMX_HISTORY_CACHE_KEY = "htmx-history-cache";

export interface PageProtocol {
  readonly navigationVersion: string;
  readonly buildId: string;
}

function readUniqueMeta(root: ParentNode, selector: string): string | null {
  const elements = root.querySelectorAll<HTMLMetaElement>(selector);
  if (elements.length !== 1) {
    return null;
  }

  const value = elements[0].content.trim();
  return value || null;
}

export function readPageProtocol(root: ParentNode): PageProtocol | null {
  const navigationVersion = readUniqueMeta(root, NAVIGATION_VERSION_SELECTOR);
  const buildId = readUniqueMeta(root, BUILD_ID_SELECTOR);
  if (!navigationVersion || !buildId) {
    return null;
  }

  return {
    navigationVersion,
    buildId,
  };
}

export function parsePageProtocol(html: string): PageProtocol | null {
  const parsed = new DOMParser().parseFromString(html, "text/html");
  return readPageProtocol(parsed);
}

export function protocolsMatch(current: PageProtocol | null, next: PageProtocol | null): boolean {
  return (
    current !== null &&
    next !== null &&
    current.navigationVersion === next.navigationVersion &&
    current.buildId === next.buildId
  );
}

export function readSessionStorage(view: Window): Storage | null {
  try {
    return view.sessionStorage;
  } catch {
    return null;
  }
}

export function syncHtmxHistoryGeneration(storage: Storage, protocol: PageProtocol | null): void {
  try {
    if (!protocol) {
      storage.removeItem(HTMX_HISTORY_CACHE_KEY);
      storage.removeItem(HISTORY_GENERATION_KEY);
      return;
    }

    const generation = `${protocol.navigationVersion}:${protocol.buildId}`;
    if (storage.getItem(HISTORY_GENERATION_KEY) === generation) {
      return;
    }

    storage.removeItem(HTMX_HISTORY_CACHE_KEY);
    storage.setItem(HISTORY_GENERATION_KEY, generation);
  } catch {
    return;
  }
}
