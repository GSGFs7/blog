import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTerminal, resetXterm, xterm } from "../../test/python-repl";

describe("Python REPL output scheduling", () => {
  beforeEach(resetXterm);

  it("serializes terminal output writes", async () => {
    xterm.autoFlush = false;
    const terminal = createTerminal();

    terminal.message("first");
    terminal.message("second");

    await vi.waitFor(() => expect(xterm.writes).toEqual(["first"]));
    xterm.pendingWrites.shift()?.();
    await vi.waitFor(() => expect(xterm.writes).toEqual(["first", "second"]));
    xterm.pendingWrites.shift()?.();
  });

  it("clears loading output after its write completes", async () => {
    xterm.autoFlush = false;
    const terminal = createTerminal();

    terminal.message("Loading Python…\r\n");
    terminal.clear();

    await vi.waitFor(() => expect(xterm.writes).toEqual(["Loading Python…\r\n"]));
    expect(xterm.clearCount).toBe(0);
    xterm.pendingWrites.shift()?.();
    await vi.waitFor(() => expect(xterm.clearCount).toBe(1));
  });

  it("batches byte output into one terminal write per frame", async () => {
    const terminal = createTerminal();

    terminal.print(102);
    terminal.print(105);
    terminal.print(114);
    terminal.print(115);
    terminal.print(116);

    expect(xterm.writes).toEqual([]);
    await vi.waitFor(() => expect(xterm.writes).toHaveLength(1));
    expect(xterm.writes[0]).toEqual(Uint8Array.from([102, 105, 114, 115, 116]));
  });

  it("flushes buffered output before starting a prompt", async () => {
    xterm.autoFlush = false;
    const terminal = createTerminal();

    terminal.print(62);
    const input = terminal.prompt();

    await vi.waitFor(() => expect(xterm.writes).toEqual([Uint8Array.of(62)]));
    expect(xterm.markers).toEqual([]);
    xterm.pendingWrites.shift()?.();
    await vi.waitFor(() => expect(xterm.writes).toEqual([Uint8Array.of(62), ""]));
    xterm.pendingWrites.shift()?.();
    await vi.waitFor(() => expect(xterm.markers).toHaveLength(1));

    xterm.autoFlush = true;
    xterm.dataHandler?.("\r");
    await expect(input).resolves.toBe("\n");
  });
});
