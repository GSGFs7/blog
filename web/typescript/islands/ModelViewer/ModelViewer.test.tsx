import { cleanup, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import ModelViewer from "./ModelViewer.island";

vi.mock("@google/model-viewer", () => ({}));

const defaultSource = "https://static.gsgfs.moe/blog/creeper.glb";

beforeEach(() => {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(private callback: IntersectionObserverCallback) {}
      observe() {
        this.callback(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      }
      disconnect() {}
    },
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function currentViewer() {
  await waitFor(() => expect(document.querySelector("model-viewer")).not.toBeNull());
  return document.querySelector("model-viewer")!;
}

test.each([undefined, "", "   ", "javascript:alert(1)", "https://["])(
  "uses the default model for missing or invalid source %s",
  async (src) => {
    render(() => <ModelViewer src={src} />);
    expect((await currentViewer()).src).toBe(defaultSource);
  },
);

test("falls back once and ignores events from the replaced model", async () => {
  render(() => <ModelViewer src="https://example.com/model.glb" alt="Custom model" />);
  const original = await currentViewer();
  expect(original.src).toBe("https://example.com/model.glb");
  original.dispatchEvent(new Event("error"));
  const fallback = await currentViewer();
  expect(fallback).not.toBe(original);
  expect(fallback.src).toBe(defaultSource);
  expect(fallback.alt).toBe("Creeper 3D model");
  original.dispatchEvent(new Event("error"));
  expect(document.querySelector("model-viewer")).toBe(fallback);
  fallback.dispatchEvent(new Event("error"));
  expect(document.querySelector("model-viewer")).toBeNull();
  expect(screen.getByRole("status")).toHaveTextContent("Model load failed");
});

test("clears the loading status when the fallback loads", async () => {
  render(() => <ModelViewer src="https://example.com/model.glb" />);
  (await currentViewer()).dispatchEvent(new Event("error"));
  (await currentViewer()).dispatchEvent(new Event("load"));
  expect(screen.queryByRole("status")).toBeNull();
});
