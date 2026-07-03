const PYTHON_WORKER_URL = "https://static.gsgfs.moe/python3.15-wasm/python.worker.mjs";

// 'python.worker.mjs' provide this interface
export type PythonWorkerMessage =
  | { type: "ready" }
  | { type: "stdout"; stdout: number }
  | { type: "stderr"; stderr: number }
  | { type: "stdin"; buffer: SharedArrayBuffer }
  | { type: "finished"; returnCode: number };

interface PythonWorkerCallbacks {
  onReady: () => void;
  onStdin: (buffer: SharedArrayBuffer) => Promise<string> | string;
  onStdout: (charCode: number) => void;
  onStderr: (charCode: number) => void;
  onFinished: (returnCode: number) => void;
  onError: (errorMessage: string) => void;
}

// Python WASM worker manager
export class PythonWorker {
  private worker: Worker | null = null;
  private bootstrapURL: string | null = null;

  constructor(private readonly callbacks: PythonWorkerCallbacks) {}

  init() {
    if (typeof SharedArrayBuffer === "undefined" || !globalThis.crossOriginIsolated) {
      this.callbacks.onError("SharedArrayBuffer is unavailable. This page requires COOP and COEP headers.");
      return;
    }

    // by-pass cross-domain issue
    const pythonWorkerURL = new URL(PYTHON_WORKER_URL).href;
    this.bootstrapURL = URL.createObjectURL(
      new Blob([`import ${JSON.stringify(pythonWorkerURL)};`], { type: "text/javascript" }),
    );
    this.worker = new Worker(this.bootstrapURL, { type: "module" });
    this.worker.addEventListener("message", (e) => this.handleMessage(e));
    this.worker.addEventListener("error", (e) => this.handleError(e));
  }

  run(code?: string) {
    if (!this.worker) {
      return;
    }

    // `code.interact` keep python running in backend
    const args = code === undefined ? ["-i"] : ["-c", code];
    this.worker.postMessage({ type: "run", args, files: {} });
  }

  terminate() {
    this.worker?.terminate();
    this.worker = null;
    if (this.bootstrapURL) {
      URL.revokeObjectURL(this.bootstrapURL);
      this.bootstrapURL = null;
    }
  }

  private sendStdin(buffer: SharedArrayBuffer, value: string) {
    const sharedBuffer = new Int32Array(buffer);
    const bytes = new TextEncoder().encode(value);

    // atomics write data
    if (bytes.length > sharedBuffer.length - 1) {
      // value too large
      this.callbacks.onError(`\nInput is limited to ${sharedBuffer.length - 1} bytes.\n`);
      Atomics.store(sharedBuffer, 0, 0);
    } else {
      sharedBuffer.set(bytes, 1);
      Atomics.store(sharedBuffer, 0, bytes.length);
    }
    Atomics.notify(sharedBuffer, 0, 1);
  }

  private async handleMessage(event: MessageEvent<PythonWorkerMessage>) {
    if (event.currentTarget !== this.worker) {
      return;
    }

    const message = event.data;
    switch (message.type) {
      case "ready": {
        this.callbacks.onReady();
        break;
      }
      case "stdin": {
        const input = await this.callbacks.onStdin(message.buffer);
        this.sendStdin(message.buffer, input);
        break;
      }
      case "stdout": {
        this.callbacks.onStdout(message.stdout);
        break;
      }
      case "stderr": {
        this.callbacks.onStderr(message.stderr);
        break;
      }
      case "finished": {
        this.callbacks.onFinished(message.returnCode);
        this.terminate();
        break;
      }
    }
  }

  private handleError(event: ErrorEvent) {
    if (event.currentTarget !== this.worker) {
      return;
    }

    this.callbacks.onError(event.message || `Failed to load ${PYTHON_WORKER_URL}`);
    this.terminate();
  }
}
