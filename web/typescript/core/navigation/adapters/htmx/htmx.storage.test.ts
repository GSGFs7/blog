import { expect, test, vi } from "vitest";

const htmxMock = vi.hoisted(() => ({
  config: {
    includeIndicatorStyles: true,
  },
}));
const setupHtmxPageLifecycle = vi.hoisted(() => vi.fn());

vi.mock("htmx.org", () => ({
  default: htmxMock,
}));
vi.mock("htmx-ext-head-support", () => ({}));
vi.mock("htmx-ext-preload", () => ({}));
vi.mock("./adapter", () => ({
  setupHtmxPageLifecycle,
}));

test("registers the lifecycle adapter when the session storage getter throws", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(window, "sessionStorage");
  Object.defineProperty(window, "sessionStorage", {
    configurable: true,
    get() {
      throw new DOMException("denied", "SecurityError");
    },
  });

  try {
    await import("./bootstrap");
  } finally {
    if (descriptor) {
      Object.defineProperty(window, "sessionStorage", descriptor);
    }
  }

  expect(setupHtmxPageLifecycle).toHaveBeenCalledOnce();
  expect(setupHtmxPageLifecycle).toHaveBeenCalledWith(document, {
    currentProtocol: null,
  });
  expect(window.htmx).toBe(htmxMock);
});
