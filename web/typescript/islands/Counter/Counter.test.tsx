import { fireEvent, render, screen } from "@solidjs/testing-library";
import { expect } from "vitest";

import { Counter } from "./Counter.island";

test("increments count", async () => {
  render(() => <Counter />);
  fireEvent.click(screen.getByRole("button"));
  expect(screen.getByText("Count: 1")).toBeInTheDocument();
});
