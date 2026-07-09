import { beforeEach, describe, expect, it, vi } from "vitest";

const xterm = vi.hoisted(() => ({
  autoFlush: true,
  clearCount: 0,
  cols: 80,
  dataHandler: undefined as ((data: string) => void) | undefined,
  markers: [] as Array<{ line: number; isDisposed: boolean; dispose: () => void }>,
  pendingWrites: [] as Array<() => void>,
  writes: [] as Array<string | Uint8Array>,
}));

vi.mock("@xterm/addon-fit", () => ({
  FitAddon: class {
    fit() {}
  },
}));

vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    get cols() {
      return xterm.cols;
    }

    buffer = {
      active: {
        baseY: 0,
        cursorY: 0,
        cursorX: 4,
      },
    };

    loadAddon() {}

    onData(handler: (data: string) => void) {
      xterm.dataHandler = handler;
    }

    write(data: string | Uint8Array, callback?: () => void) {
      xterm.writes.push(data);
      if (!callback) {
        return;
      }

      if (xterm.autoFlush) {
        callback();
      } else {
        xterm.pendingWrites.push(callback);
      }
    }

    registerMarker() {
      const marker = {
        line: 0,
        isDisposed: false,
        dispose() {
          marker.isDisposed = true;
        },
      };
      xterm.markers.push(marker);
      return marker;
    }

    clear() {
      xterm.clearCount++;
    }

    dispose() {}
  },
}));

import { Terminal } from "./terminal";
import { XtermBackend } from "./terminal-backend-xterm";

describe("Python REPL terminal", () => {
  beforeEach(() => {
    xterm.autoFlush = true;
    xterm.clearCount = 0;
    xterm.cols = 80;
    xterm.dataHandler = undefined;
    xterm.markers = [];
    xterm.pendingWrites = [];
    xterm.writes = [];
  });

  async function startPrompt(terminal: Terminal) {
    const markerCount = xterm.markers.length;
    const input = terminal.prompt();
    await vi.waitFor(() => expect(xterm.markers).toHaveLength(markerCount + 1));
    await Promise.resolve();
    return { input };
  }

  async function enter(terminal: Terminal, value: string) {
    const { input } = await startPrompt(terminal);
    xterm.dataHandler?.(value);
    xterm.dataHandler?.("\r");
    return input;
  }

  function createTerminal() {
    return new Terminal("interrupt", new XtermBackend());
  }

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

  it("wraps double-width characters before the terminal boundary", async () => {
    xterm.cols = 6;
    const terminal = createTerminal();

    await enter(terminal, "a你");

    expect(xterm.writes).toContain("\x1b[0Ja\r\n你");
  });
});
