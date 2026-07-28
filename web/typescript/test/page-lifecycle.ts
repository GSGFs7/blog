import { APP_PAGE_EVENT, emitPageEvent } from "../core/navigation";

let nextNavigationId = 0;

export function runPageSwap(swap: () => void, targetDocument: Document = window.document): number {
  const navigationId = ++nextNavigationId;
  const detail = {
    navigationId,
    root: targetDocument.body,
  };

  emitPageEvent(targetDocument, APP_PAGE_EVENT.beforeSwap, detail);
  swap();
  emitPageEvent(targetDocument, APP_PAGE_EVENT.afterSwap, detail);
  return navigationId;
}
