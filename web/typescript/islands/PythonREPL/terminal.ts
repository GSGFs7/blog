import stringWidth from "fast-string-width";

import type { TerminalBackend, TerminalInput } from "./terminal-backend";

// grapheme?
// JS use UTF-16 encoding chars
// some complex char encoding with more then 1 normal char length
// use grapheme split chars currently
const segmenter = new Intl.Segmenter(undefined, {
  granularity: "grapheme",
});

function splitGraphemes(value: string): string[] {
  return [...segmenter.segment(value)].map(({ segment }) => segment);
}

function isControlCharacter(value: string): boolean {
  const codePoint = value.codePointAt(0);
  return value.length === 1 && codePoint !== undefined && (codePoint < 0x20 || codePoint === 0x7f);
}

// current input line
class LineEditor {
  private graphemes: string[] = [];
  private cursor: number = 0;

  get value(): string {
    return this.graphemes.join("");
  }

  get cursorIndex(): number {
    return this.cursor;
  }

  get parts(): string[] {
    // shallow copy shared data
    return [...this.graphemes];
  }

  get beforeCursor(): string {
    return this.graphemes.slice(0, this.cursor).join("");
  }

  get afterCursor(): string {
    return this.graphemes.slice(this.cursor).join("");
  }

  get isEmpty(): boolean {
    return this.graphemes.length === 0;
  }

  setValue(value: string): void {
    this.graphemes = splitGraphemes(value);
    this.cursor = this.graphemes.length;
  }

  insert(value: string): void {
    const inserted = splitGraphemes(value);
    this.graphemes.splice(this.cursor, 0, ...inserted);
    this.cursor += inserted.length;
  }

  backspace(): void {
    if (this.cursor === 0) {
      return;
    }

    this.graphemes.splice(this.cursor - 1, 1);
    this.cursor--;
  }

  delete(): void {
    if (this.cursor >= this.graphemes.length) {
      return;
    }

    this.graphemes.splice(this.cursor, 1);
  }

  left(): void {
    this.cursor = Math.max(0, this.cursor - 1);
  }

  right(): void {
    this.cursor = Math.min(this.graphemes.length, this.cursor + 1);
  }

  home(): void {
    this.cursor = 0;
  }

  end(): void {
    this.cursor = this.graphemes.length;
  }

  clear(): void {
    this.graphemes = [];
    this.cursor = 0;
  }
}

class InputRenderer {
  private queue: Promise<void> = Promise.resolve();

  constructor(private readonly backend: TerminalBackend) {}

  begin(): Promise<void> {
    return this.enqueue(() => this.backend.beginInput());
  }

  render(editor: LineEditor): Promise<void> {
    const input: TerminalInput = { graphemes: editor.parts, cursorIndex: editor.cursorIndex };
    return this.enqueue(() => this.backend.renderInput(input));
  }

  async commit(editor: LineEditor, suffix = ""): Promise<void> {
    return this.render(editor).then(() => this.enqueue(() => this.backend.commitInput(suffix)));
  }

  output(data: string | Uint8Array): Promise<void> {
    return this.enqueue(() => this.backend.write(data));
  }

  clear(): Promise<void> {
    return this.enqueue(async () => this.backend.clear());
  }

  private enqueue(operation: () => Promise<void>): Promise<void> {
    this.queue = this.queue.then(operation, operation);
    return this.queue;
  }
}

class BufferQueue {
  private readonly buffer: string[] = [];

  addData(data: string) {
    // use '\n'
    data = data.replace(/\r\n?/g, "\n");

    const lines = data.match(/.*(?:\n|$)/g) ?? [];
    if (this.lastLinesIncomplete() && lines.length > 0) {
      this.buffer[this.buffer.length - 1] += lines.shift();
    }
    this.buffer.push(...lines.filter(Boolean));
  }

  hasLineReady() {
    return !this.isEmpty() && this.buffer[0].endsWith("\n");
  }

  lastLinesIncomplete() {
    return !this.isEmpty() && !this.buffer.at(-1)?.endsWith("\n");
  }

  nextLine() {
    return this.buffer.shift() ?? "";
  }

  private isEmpty() {
    return this.buffer.length === 0;
  }
}

export class Terminal {
  private readonly editor: LineEditor = new LineEditor();
  private readonly renderer: InputRenderer; // init with a backend
  private readonly historyDrafts: Map<number, string> = new Map<number, string>();
  private readonly inputBuffer: BufferQueue = new BufferQueue();
  private readonly history: string[] = [];
  private readonly outputBuffer: number[] = [];

  // is waiting user input
  private activeInput: boolean = false;
  // history index (-1 mean new command)
  private historyIndex: number = -1;
  // save new command
  private beforeHistoryNavigation: string = "";
  private resolveInput?: (value: string) => void;
  private outputFrame?: number;
  private resizeFrame?: number;
  private resizeObserver?: ResizeObserver;

  constructor(
    private readonly interruptText: string,
    private readonly backend: TerminalBackend,
  ) {
    this.renderer = new InputRenderer(backend);
    this.backend.onData((data) => this.handleData(data));
  }

  open(container: HTMLElement) {
    this.backend.open(container);
    this.resizeObserver = new ResizeObserver(() => this.scheduleFit());
    this.resizeObserver.observe(container);
    this.scheduleFit();
  }

  dispose() {
    this.resizeObserver?.disconnect();
    if (this.outputFrame !== undefined) {
      cancelAnimationFrame(this.outputFrame);
      this.outputFrame = undefined;
    }
    this.outputBuffer.length = 0;
    if (this.resizeFrame !== undefined) {
      cancelAnimationFrame(this.resizeFrame);
    }
    this.backend.dispose();
  }

  clear(): void {
    this.flushOutput();
    void this.renderer.clear();
  }

  message(text: string): void {
    this.flushOutput();
    void this.renderer.output(text);
  }

  print(charCode: number): void {
    if (charCode) {
      this.outputBuffer.push(charCode);
      this.outputFrame ??= requestAnimationFrame(() => {
        this.outputFrame = undefined;
        this.flushOutput();
      });
    }
  }

  async prompt(): Promise<string> {
    this.flushOutput();
    await this.renderer.begin();

    if (this.inputBuffer.hasLineReady()) {
      const line = this.inputBuffer.nextLine();
      this.editor.setValue(line.replace(/\n$/, ""));

      await this.renderer.commit(this.editor);
      this.saveHistoryEntry(line);
      this.editor.clear();
      this.resetHistoryNavigation();

      return line;
    }

    if (this.inputBuffer.lastLinesIncomplete()) {
      this.editor.setValue(this.inputBuffer.nextLine());
      await this.renderer.render(this.editor);
    }

    this.activeInput = true;

    // ?
    return new Promise((resolve) => {
      this.resolveInput = resolve;
    });
  }

  // --- handler ---

  private handleData(data: string) {
    if (data.startsWith("\x1b")) {
      this.handleEscapeSequence(data);
      return;
    }

    if (data.length > 1 && /[\r\n]/.test(data)) {
      this.handlePaste(data);
      return;
    }

    if (!this.activeInput) {
      if (!isControlCharacter(data)) {
        this.inputBuffer.addData(data);
      }
      return;
    }

    if (isControlCharacter(data)) {
      this.handleControlCharacter(data);
      return;
    }

    this.insertAtCursor(data);
    this.updateHistoryDraft();
  }

  private handlePaste(data: string) {
    const normalized = data.replace(/\r\n?/g, "\n");

    if (!this.activeInput) {
      this.inputBuffer.addData(normalized);
      return;
    }

    if (!normalized.includes("\n")) {
      this.insertAtCursor(normalized);
      return;
    }

    const combined = this.editor.beforeCursor + normalized + this.editor.afterCursor;
    const newlineIndex = combined.indexOf("\n");
    const firstLine = combined.slice(0, newlineIndex);
    const remaining = combined.slice(newlineIndex + 1);
    this.editor.setValue(firstLine);
    this.inputBuffer.addData(remaining);
    this.completeInput(`${firstLine}\n`);
  }

  private handleEscapeSequence(data: string) {
    if (!this.activeInput) {
      return;
    }

    switch (data.slice(1)) {
      case "[A": {
        this.historyBack();
        break;
      }
      case "[B": {
        this.historyForward();
        break;
      }
      case "[C": {
        this.cursorRight();
        break;
      }
      case "[D": {
        this.cursorLeft();
        break;
      }
      case "[F":
      case "[4~": {
        this.cursorEnd();
        break;
      }
      case "[H":
      case "[1~": {
        this.cursorHome();
        break;
      }
      case "[3~": {
        this.deleteAtCursor();
        break;
      }
    }
  }

  handleControlCharacter(data: string) {
    switch (data) {
      case "\n":
      case "\r": {
        this.submitInput();
        break;
      }
      case "\x03": {
        this.editor.end();
        this.completeInput(`${this.interruptText}\n`, "^C");
        break;
      }
      case "\x04": {
        if (this.editor.isEmpty) {
          this.completeInput("");
        }
        break;
      }
      case "\x08":
      case "\x7f": {
        this.eraseBeforeCursor();
        break;
      }
      case "\x09": {
        // 4 width tab by default
        const column = stringWidth(this.editor.beforeCursor);
        this.insertAtCursor(" ".repeat(4 - (column % 4)));
        break;
      }
      case "\x0c":
        this.clear();
        break;
    }
  }

  // --- utils ---

  private flushOutput() {
    if (this.outputFrame !== undefined) {
      cancelAnimationFrame(this.outputFrame);
      this.outputFrame = undefined;
    }
    if (this.outputBuffer.length === 0) {
      return;
    }

    const output = Uint8Array.from(this.outputBuffer);
    this.outputBuffer.length = 0;
    void this.renderer.output(output);
  }

  private scheduleFit() {
    if (this.resizeFrame !== undefined) {
      cancelAnimationFrame(this.resizeFrame);
    }
    this.resizeFrame = requestAnimationFrame(() => {
      this.resizeFrame = undefined;
      this.backend.fit();

      if (this.activeInput) {
        void this.renderer.render(this.editor);
      }
    });
  }

  private replaceInput(value: string) {
    this.editor.setValue(value);
    void this.renderer.render(this.editor);
  }

  private completeInput(value: string, suffix = "") {
    if (!this.activeInput) {
      return;
    }

    this.activeInput = false;

    const resolve = this.resolveInput;
    this.resolveInput = undefined;

    void this.renderer.commit(this.editor, suffix).then(() => {
      this.saveHistoryEntry(value);
      this.editor.clear();
      this.resetHistoryNavigation();
      resolve?.(value);
    });
  }

  private submitInput() {
    const value = `${this.editor.value}\n`;
    this.completeInput(value);
  }

  // --- cursor & edit ---

  private edit(action: () => void): void {
    action();
    this.updateHistoryDraft();
    void this.renderer.render(this.editor);
  }

  private insertAtCursor(data: string) {
    this.edit(() => this.editor.insert(data));
  }

  private eraseBeforeCursor() {
    this.edit(() => this.editor.backspace());
  }

  private deleteAtCursor() {
    this.edit(() => this.editor.delete());
  }

  private cursorLeft() {
    this.editor.left();
    void this.renderer.render(this.editor);
  }

  private cursorRight() {
    this.editor.right();
    void this.renderer.render(this.editor);
  }

  private cursorHome() {
    this.editor.home();
    void this.renderer.render(this.editor);
  }

  private cursorEnd() {
    this.editor.end();
    void this.renderer.render(this.editor);
  }

  // --- history ---

  /**
   * "up" key
   */
  private historyBack() {
    if (this.history.length === 0) {
      return;
    }

    if (this.historyIndex === -1) {
      // -1: new input line
      this.beforeHistoryNavigation = this.editor.value;
      this.historyIndex = this.history.length - 1;
    } else if (this.historyIndex > 0) {
      this.historyIndex--;
    }

    this.replaceInput(this.historyDrafts.get(this.historyIndex) ?? this.history[this.historyIndex]);
  }

  /**
   * "down" key
   */
  private historyForward() {
    if (this.historyIndex === -1) {
      return;
    }

    if (this.historyIndex < this.history.length - 1) {
      this.historyIndex += 1;
      this.replaceInput(this.historyDrafts.get(this.historyIndex) ?? this.history[this.historyIndex]);
    } else {
      // back to new line
      this.historyIndex = -1;
      this.replaceInput(this.beforeHistoryNavigation);
    }
  }

  private updateHistoryDraft() {
    if (this.historyIndex === -1) {
      this.beforeHistoryNavigation = this.editor.value;
    } else {
      this.historyDrafts.set(this.historyIndex, this.editor.value);
    }
  }

  private resetHistoryNavigation() {
    this.historyIndex = -1;
    this.beforeHistoryNavigation = "";
    this.historyDrafts.clear();
  }

  private saveHistoryEntry(value: string) {
    const entry = value.endsWith("\n") ? value.slice(0, -1) : value;
    if (!entry.trim() || entry === this.interruptText) {
      return;
    }

    this.history.push(entry);
  }
}
