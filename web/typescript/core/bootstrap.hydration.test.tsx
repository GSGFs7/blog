import { fireEvent, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, expect } from "vitest";

import { COMPONENTS } from "../islands";
import { bootstrap, cleanup, setupIslands } from "./bootstrap";

type HydrationGlobal = typeof globalThis & {
  _$HY?: {
    events: unknown[];
    completed: WeakSet<object>;
    r: Record<string, unknown>;
    fe: () => void;
  };
};

const hydrationGlobal = globalThis as HydrationGlobal;

setupIslands(COMPONENTS);

beforeEach(() => {
  document.body.innerHTML = "";

  // init hydration runtime
  hydrationGlobal._$HY = {
    events: [],
    completed: new WeakSet(),
    r: {},
    fe() {},
  };
});

afterEach(() => {
  cleanup(document);
  document.body.innerHTML = "";
  delete hydrationGlobal._$HY;
});

test("hydrates SSR markup without replacing it", async () => {
  document.body.innerHTML = `<div data-solid-island="Counter" data-solid-ssr data-props='{"initial":1024}'><div data-hk="00"><span>Count: <!--$-->0<!--/--></span><button type="button" class="m-2 rounded-md border border-white/30 bg-gray-500/30 px-2 text-white">+1</button></div></div>`;

  const island = document.querySelector<HTMLElement>("[data-solid-island]");
  expect(island).not.toBeNull();

  // save this element
  const ssrRoot = island!.firstElementChild;

  bootstrap();

  await waitFor(() => expect(screen.getByText("Count: 1024")).toBeInTheDocument());

  // `hydrate()` should re-use the DOM element
  expect(island?.firstElementChild).toBe(ssrRoot);

  fireEvent.click(screen.getByRole("button"));
  expect(screen.getByText("Count: 1025")).toBeInTheDocument();
  expect(island!.firstElementChild).toBe(ssrRoot);
});
