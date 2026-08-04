import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { runPageSwap } from "../test/page-lifecycle";
import { bootstrap, cleanup, setupIslands } from "./bootstrap";
import { APP_PAGE_EVENT, emitPageEvent } from "./navigation";

const solidWeb = vi.hoisted(() => {
  const dispose = vi.fn();
  return {
    dispose,
    hydrate: vi.fn(() => dispose),
    render: vi.fn(() => dispose),
  };
});

vi.mock("solid-js/web", async (importOriginal) => ({
  ...(await importOriginal<typeof import("solid-js/web")>()),
  hydrate: solidWeb.hydrate,
  render: solidWeb.render,
}));

let loadComponent = async () => () => null;

setupIslands({ Example: () => loadComponent() });

beforeEach(() => {
  loadComponent = async () => () => null;
  solidWeb.dispose.mockClear();
  solidWeb.hydrate.mockReset().mockReturnValue(solidWeb.dispose);
  solidWeb.render.mockReset().mockReturnValue(solidWeb.dispose);
  document.body.replaceChildren();
});

afterEach(() => {
  cleanup(document);
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

test("uses hydration for server-rendered islands", async () => {
  document.body.innerHTML = `
    <div data-solid-island="Example" data-solid-ssr data-props='{"initial":1024}'>
      <p>server markup</p>
    </div>
  `;

  const island = document.querySelector<HTMLElement>("[data-solid-island]");
  expect(island).not.toBeNull();
  const ssrRoot = island!.firstElementChild;

  bootstrap();

  await vi.waitFor(() => expect(solidWeb.hydrate).toHaveBeenCalledOnce());

  expect(solidWeb.hydrate).toHaveBeenCalledWith(expect.any(Function), island);
  expect(solidWeb.render).not.toHaveBeenCalled();
  expect(island?.firstElementChild).toBe(ssrRoot);
});

test("falls back to client rendering when hydration fails", async () => {
  const warning = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  solidWeb.hydrate.mockImplementationOnce(() => {
    throw new Error("hydration failed");
  });
  document.body.innerHTML = `
    <div data-solid-island="Example" data-solid-ssr>
      <p>server markup</p>
    </div>
  `;

  const island = document.querySelector<HTMLElement>("[data-solid-island]");
  expect(island).not.toBeNull();

  bootstrap();

  await vi.waitFor(() => expect(solidWeb.render).toHaveBeenCalledOnce());

  expect(island).toBeEmptyDOMElement();
  expect(warning).toHaveBeenCalledWith(
    "Failed to hydrate Solid island 'Example', falling back to CSR.",
    expect.any(Error),
  );
});

test("cleans up and mounts islands through the page lifecycle", async () => {
  document.body.innerHTML = '<div data-solid-island="Example"></div>';
  bootstrap();
  await vi.waitFor(() => expect(solidWeb.render).toHaveBeenCalledOnce());

  runPageSwap(() => {
    document.body.innerHTML = '<div data-solid-island="Example"></div>';
  });

  expect(solidWeb.dispose).toHaveBeenCalledOnce();
  await vi.waitFor(() => expect(solidWeb.render).toHaveBeenCalledTimes(2));
});

test("does not mount an island whose page was replaced during component loading", async () => {
  let resolveComponent: ((component: () => null) => void) | undefined;
  loadComponent = () =>
    new Promise((resolve) => {
      resolveComponent = resolve;
    });
  document.body.innerHTML = '<div data-solid-island="Example"></div>';

  bootstrap();
  emitPageEvent(document, APP_PAGE_EVENT.beforeSwap, {
    navigationId: 1,
    root: document.body,
  });
  document.body.replaceChildren();
  resolveComponent?.(() => null);

  await vi.waitFor(() => expect(resolveComponent).toBeDefined());
  expect(solidWeb.hydrate).not.toHaveBeenCalled();
  expect(solidWeb.render).not.toHaveBeenCalled();
});
