export const APP_PAGE_EVENT = {
  navigationStart: "app:navigation-start",
  navigationEnd: "app:navigation-end",
  navigationError: "app:navigation-error",
  beforeSwap: "app:before-swap",
  afterSwap: "app:after-swap",
} as const;

export type NavigationType = "push" | "pop" | "replace";
export type NavigationSource = "memory" | "fetch";
export type NavigationOutcome = "completed" | "cancelled" | "fallback";
export type NavigationPhase = "request" | "validation" | "swap" | "settle";

export interface PageSwapDetail {
  readonly navigationId: number;
  readonly root: HTMLElement;
}

export interface PageNavigationDetail extends PageSwapDetail {
  readonly from: URL;
  readonly requestedUrl: URL;
  readonly finalUrl?: URL;
  readonly navigationType: NavigationType;
  readonly source: NavigationSource;
  readonly deliverySource?: "service-worker" | "origin" | "cloudflare" | "unknown";
}

export interface PageNavigationEndDetail extends PageNavigationDetail {
  readonly outcome: NavigationOutcome;
}

export interface PageNavigationErrorDetail extends PageNavigationDetail {
  readonly phase: NavigationPhase;
  readonly error: unknown;
}

export interface PageEventDetailMap {
  "app:navigation-start": PageNavigationDetail;
  "app:navigation-end": PageNavigationEndDetail;
  "app:navigation-error": PageNavigationErrorDetail;
  "app:before-swap": PageSwapDetail;
  "app:after-swap": PageSwapDetail;
}

declare global {
  interface DocumentEventMap {
    "app:navigation-start": CustomEvent<PageNavigationDetail>;
    "app:navigation-end": CustomEvent<PageNavigationEndDetail>;
    "app:navigation-error": CustomEvent<PageNavigationErrorDetail>;
    "app:before-swap": CustomEvent<PageSwapDetail>;
    "app:after-swap": CustomEvent<PageSwapDetail>;
  }
}

export function emitPageEvent<K extends keyof PageEventDetailMap>(
  document: Document,
  name: K,
  detail: PageEventDetailMap[K],
): void {
  document.dispatchEvent(new CustomEvent(name, { detail }));
}
