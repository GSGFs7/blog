import { onCleanup, onMount } from "solid-js";

import { PythonWorker } from "./python.worker";
import { Terminal } from "./terminal";
import { loadTerminalBackend, type TerminalBackendName } from "./terminal-backend";

// simulate ctrl+c
const INTERRUPT_TEXT = `__WASM_REPL_CTRLC_${Date.now()}__`;
const REPL_CODE = String.raw`
import builtins
import code
import sys

def _interrupt_aware_input(prompt=""):
    line = builtins.input(prompt)
    if line.strip() == ${JSON.stringify(INTERRUPT_TEXT)}:
        raise KeyboardInterrupt()
    return line

cprt = 'Type "help", "copyright", "credits" or "license" for more information.'
banner = f"Python {sys.version} on {sys.platform}\n{cprt}"
code.interact(banner=banner, readfunc=_interrupt_aware_input, exitmsg="")
`;

interface PythonREPLProps {
  backend?: unknown;
}

export function PythonREPL(_props: Readonly<PythonREPLProps>) {
  let container: HTMLDivElement | null = null;
  let terminal: Terminal | null = null;
  let worker: PythonWorker | null = null;
  let disposed: boolean = false;

  onMount(() => {
    if (!container) {
      return;
    }

    const terminalContainer: HTMLDivElement = container;
    const backendName: TerminalBackendName = "xterm";

    void loadTerminalBackend(backendName).then(({ backend, styles }) => {
      if (disposed) {
        backend.dispose();
        return;
      }

      // setup shadow dom
      const shadowRoot = terminalContainer.attachShadow({ mode: "open" });
      const style = document.createElement("style");
      const terminalRoot = document.createElement("div");
      style.textContent = styles;
      terminalRoot.style.width = "100%";
      terminalRoot.style.height = "100%";
      shadowRoot.append(style, terminalRoot);

      // start terminal
      terminal = new Terminal(INTERRUPT_TEXT, backend);
      terminal.open(terminalRoot);
      terminal.message("Loading Python…\r\n");

      // start python worker
      worker = new PythonWorker({
        onReady: () => {
          terminal?.clear();
          worker?.run(REPL_CODE);
        },
        onStdin: () => {
          return terminal?.prompt() ?? "";
        },
        onStdout: (charCode) => {
          terminal?.print(charCode);
        },
        onStderr: (charCode) => {
          terminal?.print(charCode);
        },
        onError: (errorMessage) => {
          terminal?.message(`\r\n[Python worker error] ${errorMessage}\r\n`);
        },
        onFinished: (returnCode) => {
          terminal?.message(`\r\n[Process completed with exit code ${returnCode}]\r\n`);
        },
      });
      worker.init();
    });
  });

  onCleanup(() => {
    disposed = true;
    worker?.terminate();
    terminal?.dispose();
  });

  return <div class="h-100 w-full" ref={(element) => (container = element)} aria-label="Python REPL"></div>;
}
