import { fireEvent, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, expect, test } from "vitest";

import { COMPONENTS } from "../islands";
import { bootstrap, cleanup, setupIslands } from "./bootstrap";

setupIslands(COMPONENTS);

beforeEach(() => {
  document.body.innerHTML = "";
});

afterEach(() => {
  cleanup(document);
  document.body.innerHTML = "";
});

test("renders a non-SSR island with CSR", async () => {
  document.body.innerHTML = `
    <div data-solid-island="Counter" data-props='{"initial":1024}'>
      <p data-testid="placeholder">Loading...</p>
    </div>
  `;

  const island = document.querySelector<HTMLElement>("[data-solid-island]");
  const placeholder = screen.getByTestId("placeholder");

  expect(island).not.toBeNull();
  expect(island).not.toHaveAttribute("data-solid-ssr");

  bootstrap();

  await waitFor(() => {
    expect(screen.getByText("Count: 1024")).toBeInTheDocument();
  });

  expect(placeholder.isConnected).toBe(false);
  expect(island!.firstElementChild).not.toBe(placeholder);

  fireEvent.click(screen.getByRole("button"));
  expect(screen.getByText("Count: 1025")).toBeInTheDocument();
});

test("bootstrap does not remount an already mounted island", async () => {
  document.body.innerHTML = '<div data-solid-island="Counter"></div>';

  bootstrap();
  await waitFor(() => {
    expect(screen.getByRole("button")).toBeInTheDocument();
  });
  fireEvent.click(screen.getByRole("button"));
  expect(screen.getByText("Count: 1")).toBeInTheDocument();

  bootstrap();
  expect(screen.getByText("Count: 1")).toBeInTheDocument();
});

test("cleanup and bootstrap only affect the swapped htmx target", async () => {
  document.body.innerHTML = `
    <section id="outside">
      <div data-solid-island="Counter"></div>
    </section>
    <section id="swap-target">
      <div data-solid-island="Counter"></div>
    </section>
  `;

  bootstrap();
  await waitFor(() => {
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });
  fireEvent.click(screen.getAllByRole("button")[0]);
  expect(screen.getAllByText(/Count:/)[0]).toHaveTextContent("Count: 1");
  expect(screen.getAllByText(/Count:/)[1]).toHaveTextContent("Count: 0");

  const target = document.getElementById("swap-target");
  if (!(target instanceof HTMLElement)) {
    throw new Error("swap target not found");
  }

  cleanup(target);
  target.innerHTML = '<div data-solid-island="Counter"></div>';
  bootstrap(target);
  await waitFor(() => {
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  expect(screen.getAllByText(/Count:/)[0]).toHaveTextContent("Count: 1");
  expect(screen.getAllByText(/Count:/)[1]).toHaveTextContent("Count: 0");
});
