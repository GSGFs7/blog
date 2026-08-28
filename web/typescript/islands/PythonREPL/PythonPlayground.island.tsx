import { createSignal, onCleanup, onMount, Show } from "solid-js";

import { monaco } from "./monaco";
import { PythonWorker } from "./python.worker";

interface PythonPlaygroundProps {
  source?: unknown;
}

type RunStatus = "idle" | "loading" | "running";

const DEFAULT_SOURCE = `class C:
    def greet(self):
        return "Ciallo～(∠・ω< )⌒★"


print(C().greet())
`;

const styledShadowRoots = new WeakSet<ShadowRoot>();

// if component in the shadow DOM, add stylesheet
function mirrorMonacoStyles(root: ShadowRoot) {
  if (styledShadowRoots.has(root)) {
    return;
  }

  for (const sheet of document.styleSheets) {
    const owner = sheet.ownerNode;
    if (!(owner instanceof HTMLElement)) {
      continue;
    }

    const viteId = owner.dataset.viteDevId ?? "";
    let isMonacoStyle = viteId.includes("monaco-editor");
    if (!isMonacoStyle) {
      try {
        isMonacoStyle = Array.from(sheet.cssRules).some((rule) =>
          rule.cssText.includes(".monaco-editor"),
        );
      } catch {
        continue;
      }
    }

    if (isMonacoStyle) {
      root.prepend(owner.cloneNode(true));
    }
  }
  styledShadowRoots.add(root);
}

function readCssVariable(style: CSSStyleDeclaration, name: string) {
  return style.getPropertyValue(name).trim();
}

function defineMarkdownTheme(element: HTMLElement) {
  const style = getComputedStyle(element);
  const dark = document.documentElement.classList.contains("dark");
  const themeName = dark ? "markdown-dark" : "markdown-light";
  const border = readCssVariable(style, "--md-pre-border");
  const punctuation = readCssVariable(style, "--syn-punctuation");
  monaco.editor.defineTheme(themeName, {
    base: dark ? "vs-dark" : "vs",
    inherit: true,
    colors: {
      "editor.background": readCssVariable(style, "--md-pre-bg"),
      "editor.foreground": readCssVariable(style, "--md-fg"),
      "editorCursor.foreground": "#ffffff",
      "editor.selectionBackground": dark ? "#264054" : "#8fb4d2",
      "editor.inactiveSelectionBackground": dark ? "#253e52" : "#636e79",
      "editor.wordHighlightBackground": dark ? "#3f4249" : "#454d50",
      "editor.wordHighlightStrongBackground": dark ? "#5f686e" : "#657377",
      "editorLineNumber.foreground": readCssVariable(style, "--syn-comment"),
      "editorLineNumber.activeForeground": readCssVariable(style, "--md-fg"),
      "editorGutter.background": readCssVariable(style, "--md-pre-bg"),
      "editorWidget.background": readCssVariable(style, "--md-pre-bg"),
      "editorWidget.border": border,
      "editor.lineHighlightBorder": border,
      "editorBracketMatch.background": "#00000000",
      "editorBracketMatch.border": border,
      "editorBracketMatch.foreground": punctuation,
      "editorBracketHighlight.foreground1": punctuation,
      "editorBracketHighlight.foreground2": punctuation,
      "editorBracketHighlight.foreground3": punctuation,
      "editorBracketHighlight.foreground4": punctuation,
      "editorBracketHighlight.foreground5": punctuation,
      "editorBracketHighlight.foreground6": punctuation,
    },
    rules: [
      { token: "comment", foreground: readCssVariable(style, "--syn-comment") },
      { token: "keyword", foreground: readCssVariable(style, "--syn-keyword") },
      { token: "string", foreground: readCssVariable(style, "--syn-string") },
      { token: "number", foreground: readCssVariable(style, "--syn-constant") },
      { token: "identifier", foreground: readCssVariable(style, "--syn-variable") },
      { token: "delimiter", foreground: readCssVariable(style, "--syn-punctuation") },
    ],
  });
  return themeName;
}

export function PythonPlayground(props: Readonly<PythonPlaygroundProps>) {
  let editorContainer: HTMLDivElement;
  let editor: monaco.editor.IStandaloneCodeEditor | undefined;
  let pythonWorker: PythonWorker | undefined;

  const [_status, setStatus] = createSignal<RunStatus>("idle");
  const [output, setOutput] = createSignal("");

  const initialSource = typeof props.source === "string" ? props.source : DEFAULT_SOURCE;

  const appendOutput = (value: string) => {
    setOutput((current) => current + value);
  };

  const stop = () => {
    pythonWorker?.terminate();
    pythonWorker = undefined;
    setStatus("idle");
  };

  const _reset = () => {
    editor?.setValue(initialSource);
    setOutput("");
  };

  const run = () => {
    stop();

    const code = editor?.getValue() ?? "";
    const decoder = new TextDecoder();

    setOutput("");
    setStatus("loading");

    pythonWorker = new PythonWorker({
      onReady: () => {
        setStatus("running");
        pythonWorker?.run(code);
      },
      onStdin: (_byte) => {
        // TODO
        return "\n";
      },
      onStdout: (byte) => {
        appendOutput(decoder.decode(Uint8Array.of(byte), { stream: true }));
      },
      onStderr: (byte) => {
        appendOutput(decoder.decode(Uint8Array.of(byte), { stream: true }));
      },
      onFinished: (returnCode) => {
        appendOutput(decoder.decode());
        if (returnCode != null && returnCode !== 0) {
          appendOutput(`\n[Process exited with code ${returnCode}]\n`);
        }
        pythonWorker = undefined;
        setStatus("idle");
      },
      onError: (message) => {
        appendOutput(`\n[Python worker error] ${message}\n`);
        pythonWorker = undefined;
        setStatus("idle");
      },
    });
    pythonWorker.init();
  };

  onMount(() => {
    const root = editorContainer.getRootNode();
    if (root instanceof ShadowRoot) {
      mirrorMonacoStyles(root);
    }

    const style = getComputedStyle(editorContainer);
    const markdownFontSize = Number.parseFloat(style.fontSize) * 0.85;
    editor = monaco.editor.create(editorContainer, {
      value: initialSource,
      language: "python",
      theme: defineMarkdownTheme(editorContainer),

      automaticLayout: true,
      fontFamily: readCssVariable(style, "--font-mono"),
      fontWeight: readCssVariable(style, "--md-code-font-weight"),
      fontSize: markdownFontSize,
      lineHeight: markdownFontSize * 1.45,

      // I don't like this
      minimap: {
        enabled: false,
      },

      glyphMargin: false,
      lineNumbersMinChars: 3,

      padding: {
        top: markdownFontSize,
        bottom: markdownFontSize,
      },

      bracketPairColorization: {
        enabled: true,
      },

      cursorSmoothCaretAnimation: "on",
      smoothScrolling: true,
      scrollBeyondLastLine: false,
      renderLineHighlight: "all",
      wordWrap: "on",
      tabSize: 4,
    });

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, run);
  });

  onCleanup(() => {
    stop();

    const model = editor?.getModel();
    editor?.dispose();
    model?.dispose();
  });

  return (
    <section
      style={{
        overflow: "hidden",
        width: "100%",
        "min-width": "0",
        "margin-bottom": "1em",
        border: "1px solid var(--md-border)",
        "border-radius": "8px",
        background: "var(--md-pre-bg)",
      }}
    >
      <div
        class="h-96 w-full"
        ref={(e) => (editorContainer = e)}
        aria-label="Python playground editor"
      ></div>

      <Show when={output()}>
        <pre>{output()}</pre>
      </Show>
    </section>
  );
}

export default PythonPlayground;
