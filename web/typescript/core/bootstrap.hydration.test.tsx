import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { bootstrap, cleanup, setupIslands } from "./bootstrap";

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

setupIslands({
  Example: async () => () => null,
});

beforeEach(() => {
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
