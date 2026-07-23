import { beforeEach, describe, expect, it } from "vitest";

import { createTerminal, enter, resetXterm, startPrompt, xterm } from "../../test/python-repl";

describe("Python REPL command history", () => {
  beforeEach(resetXterm);

  it("recalls commands submitted in the current terminal", async () => {
    const terminal = createTerminal();

    await expect(enter(terminal, "first")).resolves.toBe("first\n");

    const { input: recalled } = await startPrompt(terminal);
    xterm.dataHandler?.("\x1b[A");
    xterm.dataHandler?.("\r");

    await expect(recalled).resolves.toBe("first\n");
  });

  it("keeps the original history after running an edited command", async () => {
    const terminal = createTerminal();

    await expect(enter(terminal, "first")).resolves.toBe("first\n");

    const { input: edited } = await startPrompt(terminal);
    xterm.dataHandler?.("\x1b[A");
    xterm.dataHandler?.(" edited");
    xterm.dataHandler?.("\r");
    await expect(edited).resolves.toBe("first edited\n");

    const { input: original } = await startPrompt(terminal);
    xterm.dataHandler?.("\x1b[A");
    xterm.dataHandler?.("\x1b[A");
    xterm.dataHandler?.("\r");

    await expect(original).resolves.toBe("first\n");
  });

  it("restores edited history entries while navigating", async () => {
    const terminal = createTerminal();
    await enter(terminal, "first");
    await enter(terminal, "second");

    const { input } = await startPrompt(terminal);
    xterm.dataHandler?.("\x1b[A");
    xterm.dataHandler?.(" edited");
    xterm.dataHandler?.("\x1b[A");
    xterm.dataHandler?.("\x1b[B");
    xterm.dataHandler?.("\r");

    await expect(input).resolves.toBe("second edited\n");
  });

  it("restores the current draft after leaving history", async () => {
    const terminal = createTerminal();
    await enter(terminal, "first");

    const { input } = await startPrompt(terminal);
    xterm.dataHandler?.("draft");
    xterm.dataHandler?.("\x1b[A");
    xterm.dataHandler?.("\x1b[B");
    xterm.dataHandler?.("\r");

    await expect(input).resolves.toBe("draft\n");
  });

  it("does not add blank or interrupted input to history", async () => {
    const terminal = createTerminal();
    await enter(terminal, "kept");
    await enter(terminal, "");

    const { input: interrupted } = await startPrompt(terminal);
    xterm.dataHandler?.("ignored");
    xterm.dataHandler?.("\x03");
    await expect(interrupted).resolves.toBe("interrupt\n");

    const { input: recalled } = await startPrompt(terminal);
    xterm.dataHandler?.("\x1b[A");
    xterm.dataHandler?.("\r");
    await expect(recalled).resolves.toBe("kept\n");
  });

  it("keeps history isolated between terminal instances", async () => {
    const firstTerminal = createTerminal();
    await enter(firstTerminal, "first");

    const secondTerminal = createTerminal();
    const { input } = await startPrompt(secondTerminal);
    xterm.dataHandler?.("\x1b[A");
    xterm.dataHandler?.("\r");

    await expect(input).resolves.toBe("\n");
  });
});
