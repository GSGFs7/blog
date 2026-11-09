import { cleanup, render } from "@solidjs/testing-library";
import { afterEach, expect, test, vi } from "vitest";

import { canApplyBackgroundUpdate } from "../../core/navigation/adapters/native/background-update";
import { PythonPlayground } from "./PythonPlayground.island";
import { PythonREPL } from "./PythonREPL.island";

const model = vi.hoisted(() => ({
  value: "initial",
  onChange: () => {},
}));

vi.mock("./monaco", () => ({
  monaco: {
    editor: {
      defineTheme: () => {},
      create: () => ({
        getValue: () => model.value,
        onDidChangeModelContent: (callback: () => void) => {
          model.onChange = callback;
        },
        addCommand: () => {},
        getModel: () => ({ dispose: () => {} }),
        dispose: () => {},
      }),
    },
    KeyMod: { CtrlCmd: 1 },
    KeyCode: { Enter: 1 },
  },
}));

vi.mock("./python.worker", () => ({
  PythonWorker: class {
    init() {}
    terminate() {}
  },
}));

vi.mock("./terminal", () => ({
  Terminal: class {
    open() {}
    message() {}
    dispose() {}
  },
}));

vi.mock("./terminal-backend", () => ({
  loadTerminalBackend: async () => ({ backend: { dispose() {} }, styles: "" }),
}));

afterEach(cleanup);

test("playground protects edited code and releases protection when it is restored", () => {
  model.value = "initial";
  render(() => <PythonPlayground source="initial" />);
  expect(canApplyBackgroundUpdate(document)).toBe(true);

  model.value = "unsaved code";
  model.onChange();
  expect(canApplyBackgroundUpdate(document)).toBe(false);

  model.value = "initial";
  model.onChange();
  expect(canApplyBackgroundUpdate(document)).toBe(true);
});

test.each(["keydown", "paste", "input"])(
  "REPL protects its session after %s inside the terminal shadow root",
  async (type) => {
    const result = render(() => <PythonREPL />);
    const container = result.getByLabelText("Python REPL");
    await vi.waitFor(() => expect(container.shadowRoot).not.toBeNull());
    expect(canApplyBackgroundUpdate(document)).toBe(true);

    const terminal = container.shadowRoot!.querySelector("div")!;
    terminal.addEventListener(type, (event) => event.stopPropagation());
    terminal.dispatchEvent(new Event(type, { bubbles: true, composed: true }));

    expect(document.activeElement).toBe(document.body);
    expect(canApplyBackgroundUpdate(document)).toBe(false);
  },
);
