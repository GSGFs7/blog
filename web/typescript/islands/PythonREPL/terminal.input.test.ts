import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTerminal, enter, resetXterm, startPrompt, xterm } from "../../test/python-repl";

describe("Python REPL input editing", () => {
  beforeEach(resetXterm);

  it("edits whole Unicode grapheme clusters", async () => {
    const terminal = createTerminal();
    const { input } = await startPrompt(terminal);

    xterm.dataHandler?.("A你👨‍👩‍👧‍👦");
    xterm.dataHandler?.("\x1b[D");
    xterm.dataHandler?.("\x7f");
    xterm.dataHandler?.("\r");

    await expect(input).resolves.toBe("A👨‍👩‍👧‍👦\n");
  });

  it("deletes a combining character as one grapheme", async () => {
    const terminal = createTerminal();
    const { input } = await startPrompt(terminal);

    xterm.dataHandler?.("e\u0301x");
    xterm.dataHandler?.("\x1b[D");
    xterm.dataHandler?.("\x7f");
    xterm.dataHandler?.("\r");

    await expect(input).resolves.toBe("x\n");
  });

  it("supports Delete, Home, and End", async () => {
    const terminal = createTerminal();
    const { input } = await startPrompt(terminal);

    xterm.dataHandler?.("你😀");
    xterm.dataHandler?.("\x1b[H");
    xterm.dataHandler?.("\x1b[3~");
    xterm.dataHandler?.("A");
    xterm.dataHandler?.("\x1b[F");
    xterm.dataHandler?.("B");
    xterm.dataHandler?.("\r");

    await expect(input).resolves.toBe("A😀B\n");
  });

  it("uses terminal cell width when inserting spaces for Tab", async () => {
    const terminal = createTerminal();
    const { input } = await startPrompt(terminal);

    xterm.dataHandler?.("你");
    xterm.dataHandler?.("\x09");
    xterm.dataHandler?.("\r");

    await expect(input).resolves.toBe("你  \n");
  });

  it("sends EOF only when the input is empty", async () => {
    const terminal = createTerminal();
    const { input } = await startPrompt(terminal);

    xterm.dataHandler?.("\x04");

    await expect(input).resolves.toBe("");
  });

  it("does not send EOF when the input is non-empty", async () => {
    const terminal = createTerminal();
    const { input } = await startPrompt(terminal);

    xterm.dataHandler?.("value");
    xterm.dataHandler?.("\x04");
    xterm.dataHandler?.("\r");

    await expect(input).resolves.toBe("value\n");
  });

  it("normalizes CR-only multiline paste", async () => {
    const terminal = createTerminal();
    const { input: first } = await startPrompt(terminal);

    xterm.dataHandler?.("first\rsecond\r");
    await expect(first).resolves.toBe("first\n");

    const { input: second } = await startPrompt(terminal);
    await expect(second).resolves.toBe("second\n");
  });

  it("preserves the text after the cursor during multiline paste", async () => {
    const terminal = createTerminal();
    const { input: first } = await startPrompt(terminal);

    xterm.dataHandler?.("ab");
    xterm.dataHandler?.("\x1b[D");
    xterm.dataHandler?.("X\nY");
    await expect(first).resolves.toBe("aX\n");

    const { input: second } = await startPrompt(terminal);
    xterm.dataHandler?.("\r");
    await expect(second).resolves.toBe("Yb\n");
  });

  it("buffers text received while a prompt is starting", async () => {
    const terminal = createTerminal();
    const input = terminal.prompt();

    xterm.dataHandler?.("buffered");
    await vi.waitFor(() => expect(xterm.markers).toHaveLength(1));
    await Promise.resolve();
    xterm.dataHandler?.("\r");

    await expect(input).resolves.toBe("buffered\n");
  });

  it("disposes the input marker after committing", async () => {
    const terminal = createTerminal();
    await enter(terminal, "value");

    expect(xterm.markers.at(-1)?.isDisposed).toBe(true);
  });

  it("wraps double-width characters before the terminal boundary", async () => {
    xterm.cols = 6;
    const terminal = createTerminal();

    await enter(terminal, "a你");

    expect(xterm.writes).toContain("\x1b[0Ja\r\n你");
  });
});
