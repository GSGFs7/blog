import { expect, vi } from "vitest";

import { Terminal } from "../islands/PythonREPL/terminal";
import { XtermBackend } from "../islands/PythonREPL/terminal-backend-xterm";

const xtermState = vi.hoisted(() => ({
  autoFlush: true,
  clearCount: 0,
  cols: 80,
  dataHandler: undefined as ((data: string) => void) | undefined,
  markers: [] as Array<{ line: number; isDisposed: boolean; dispose: () => void }>,
  pendingWrites: [] as Array<() => void>,
  writes: [] as Array<string | Uint8Array>,
}));

export const xterm = xtermState;

vi.mock("@xterm/addon-fit", () => ({
  FitAddon: class {
    fit() {}
  },
}));

vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    get cols() {
      return xtermState.cols;
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
      xtermState.dataHandler = handler;
    }

    write(data: string | Uint8Array, callback?: () => void) {
      xtermState.writes.push(data);
      if (!callback) {
        return;
      }

      if (xtermState.autoFlush) {
        callback();
      } else {
        xtermState.pendingWrites.push(callback);
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
      xtermState.markers.push(marker);
      return marker;
    }

    clear() {
      xtermState.clearCount++;
    }

    dispose() {}
  },
}));

export function resetXterm() {
  xterm.autoFlush = true;
  xterm.clearCount = 0;
  xterm.cols = 80;
  xterm.dataHandler = undefined;
  xterm.markers = [];
  xterm.pendingWrites = [];
  xterm.writes = [];
}

export function createTerminal() {
  return new Terminal("interrupt", new XtermBackend());
}

export async function startPrompt(terminal: Terminal) {
  const markerCount = xterm.markers.length;
  const input = terminal.prompt();
  await vi.waitFor(() => expect(xterm.markers).toHaveLength(markerCount + 1));
  await Promise.resolve();
  return { input };
}

export async function enter(terminal: Terminal, value: string) {
  const { input } = await startPrompt(terminal);
  xterm.dataHandler?.(value);
  xterm.dataHandler?.("\r");
  return input;
}
