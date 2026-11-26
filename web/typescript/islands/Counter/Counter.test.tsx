import { fireEvent, render, screen } from "@solidjs/testing-library";
import { flush } from "solid-js";
import { expect } from "vitest";

import { Counter } from "./Counter.island";

test("increments count", () => {
  render(() => <Counter />);

  fireEvent.click(screen.getByRole("button"));
  flush();

  expect(screen.getByText("Count: 1")).toBeInTheDocument();
});
