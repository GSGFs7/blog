export type TerminalBackendName = "xterm";

export interface TerminalInput {
  graphemes: readonly string[];
  cursorIndex: number;
}

export interface TerminalBackend {
  onData(handler: (data: string) => void): void;
  open(container: HTMLElement): void;
  fit(): void;
  clear(): void;
  dispose(): void;
  beginInput(): Promise<void>;
  renderInput(input: TerminalInput): Promise<void>;
  commitInput(suffix: string): Promise<void>;
  write(data: string | Uint8Array): Promise<void>;
}

export interface LoadedTerminalBackend {
  backend: TerminalBackend;
  styles: string;
}

export async function loadTerminalBackend(name: TerminalBackendName): Promise<LoadedTerminalBackend> {
  if (name === "xterm") {
    const { XtermBackend, styles } = await import("./terminal-backend-xterm");
    return { backend: new XtermBackend(), styles };
  }

  const { XtermBackend, styles } = await import("./terminal-backend-xterm");
  return { backend: new XtermBackend(), styles };
}
