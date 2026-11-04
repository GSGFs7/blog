import "monaco-editor/editor/browser/coreCommands";
import "monaco-editor/editor/contrib/bracketMatching/browser/bracketMatching";
import "monaco-editor/editor/contrib/clipboard/browser/clipboard";
import "monaco-editor/editor/contrib/comment/browser/comment";
import "monaco-editor/editor/contrib/contextmenu/browser/contextmenu";
import "monaco-editor/editor/contrib/cursorUndo/browser/cursorUndo";
import "monaco-editor/editor/contrib/find/browser/findController";
import "monaco-editor/editor/contrib/folding/browser/folding";
import "monaco-editor/editor/contrib/hover/browser/hoverContribution";
import "monaco-editor/editor/contrib/indentation/browser/indentation";
import "monaco-editor/editor/contrib/multicursor/browser/multicursor";
import "monaco-editor/editor/contrib/suggest/browser/suggestController";
import "monaco-editor/editor/contrib/tokenization/browser/tokenization";
import "monaco-editor/editor/contrib/wordHighlighter/browser/wordHighlighter";
import "monaco-editor/editor/contrib/wordOperations/browser/wordOperations";
import "monaco-editor/languages/definitions/python/register";
import * as monaco from "monaco-editor/editor/editor.api";
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
