import { vi } from "vitest";

export function waitForBehaviorMount(): Promise<void> {
  return vi.dynamicImportSettled();
}
