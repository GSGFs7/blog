import * as monaco from "monaco-editor";
import editorWorkerPath from "monaco-editor/editor/editor.worker?worker&url";

type MonacoGlobal = typeof window & {
  MonacoEnvironment?: {
    getWorker(moduleId: string, label: string): Worker;
  };
};

// HACK: avoid cross-origin
function createEditorWorker(): Worker {
  const workerUrl = new URL(editorWorkerPath, import.meta.url);
  if (workerUrl.origin === window.location.origin) {
    return new Worker(workerUrl, { type: "module" });
  }

  const bootstrapUrl = URL.createObjectURL(
    new Blob([`import ${JSON.stringify(workerUrl.href)};`], { type: "text/javascript" }),
  );
  const worker = new Worker(bootstrapUrl, { type: "module" });
  const terminate = worker.terminate.bind(worker);
  worker.terminate = () => {
    URL.revokeObjectURL(bootstrapUrl);
    terminate();
  };
  worker.addEventListener("error", () => URL.revokeObjectURL(bootstrapUrl), { once: true });
  return worker;
}

(window as MonacoGlobal).MonacoEnvironment = {
  getWorker() {
    return createEditorWorker();
  },
};

export { monaco };
