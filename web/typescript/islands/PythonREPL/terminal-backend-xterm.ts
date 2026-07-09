import { FitAddon } from "@xterm/addon-fit";
import { type IMarker, Terminal as XtermTerminal } from "@xterm/xterm";
import stringWidth from "fast-string-width";

import type { TerminalBackend, TerminalInput } from "./terminal-backend";

import xtermStyles from "@xterm/xterm/css/xterm.css?inline";

export const styles = xtermStyles;

// grapheme position
interface ScreenPoint {
  row: number;
  column: number;
}

// will be rendered input text
interface InputPaint {
  text: string;
  cursor: ScreenPoint;
}

function createInputPaint(input: TerminalInput, startColumn: number, columns: number): InputPaint {
  let row: number = 0;
  let column: number = startColumn;
  let text: string = "";
  let cursor: ScreenPoint = { row: 0, column: startColumn };
  for (let index = 0; index <= input.graphemes.length; index++) {
    if (index === input.cursorIndex) {
      cursor = { row, column };
    }

    if (index === input.graphemes.length) {
      break;
    }

    const grapheme = input.graphemes[index];
    const width = stringWidth(grapheme);
    if (column + width > columns) {
      text += "\r\n";
      row++;
      column = 0;
    }

    text += grapheme;
    column += width;
    if (column === columns) {
      text += "\r\n";
      row++;
      column = 0;
    }
  }

  return { text, cursor };
}

export class XtermBackend implements TerminalBackend {
  private readonly fitAddon: FitAddon = new FitAddon();
  private readonly terminal: XtermTerminal = new XtermTerminal({
    cols: 100,
    convertEol: true,
    cursorBlink: true,
    scrollback: 10_000,
    theme: { background: "#1a1c1f" },
    fontFamily: '"Maple Mono", "Maple Mono Normal", monospace',
    fontWeight: "400",
    fontWeightBold: "600",
  });
  private marker: IMarker | undefined = undefined;
  private originColumn: number = 0;

  constructor() {
    this.terminal.loadAddon(this.fitAddon);
  }

  onData(handler: (data: string) => void): void {
    this.terminal.onData(handler);
  }

  open(container: HTMLElement): void {
    this.terminal.open(container);
  }

  fit(): void {
    this.fitAddon.fit();
  }

  clear(): void {
    this.terminal.clear();
  }

  dispose(): void {
    this.marker?.dispose();
    this.terminal.dispose();
  }

  async beginInput(): Promise<void> {
    await this.write("");
    this.marker?.dispose();
    this.marker = this.terminal.registerMarker(0);
    this.originColumn = this.terminal.buffer.active.cursorX;
  }

  async renderInput(input: TerminalInput): Promise<void> {
    if (!this.marker || this.marker.isDisposed) {
      return;
    }

    const paint = createInputPaint(input, this.originColumn, this.terminal.cols);
    await this.moveTo(this.marker.line, this.originColumn);
    await this.write(`\x1b[0J${paint.text}`);
    await this.moveTo(this.marker.line + paint.cursor.row, paint.cursor.column);
  }

  async commitInput(suffix: string): Promise<void> {
    await this.write(`${suffix}\r\n`);
    this.marker?.dispose();
    this.marker = undefined;
  }

  write(data: string | Uint8Array): Promise<void> {
    return new Promise((resolve) => {
      this.terminal.write(data, resolve);
    });
  }

  private moveTo(line: number, column: number): Promise<void> {
    const buffer = this.terminal.buffer.active;
    const currentLine = buffer.baseY + buffer.cursorY;
    const rowDifference = line - currentLine;

    let sequence = "";
    if (rowDifference < 0) {
      sequence += `\x1b[${-rowDifference}A`;
    } else if (rowDifference > 0) {
      sequence += `\x1b[${rowDifference}B`;
    }
    sequence += `\x1b[${column + 1}G`;
    return this.write(sequence);
  }
}
