import { createEffect, createSignal, onCleanup } from "solid-js";

import { bootstrap, cleanup } from "../../core/bootstrap";

export function AdminPostEditor(props: Readonly<{ textarea: HTMLTextAreaElement }>) {
  let previewContainerRef: HTMLDivElement | undefined;
  let renderRequestId = 0;
  const katexCssUrl = props.textarea.dataset.katexCssUrl || "/static/katex/katex.min.css";
  const markdownCssUrl = props.textarea.dataset.markdownCssUrl || "";
  const tailwindCssUrl = props.textarea.dataset.tailwindCssUrl || "";

  const [source, setSource] = createSignal(props.textarea.value);
  const [debouncedSource, setDebouncedSource] = createSignal(source());
  const [previewHtml, setPreviewHtml] = createSignal("");
  const [isDark, setIsDark] = createSignal(true);

  // debounc 300ms
  createEffect(() => {
    const val = source();
    const timer = setTimeout(() => setDebouncedSource(val), 300);
    onCleanup(() => clearTimeout(timer));
  });

  // render markdown
  createEffect(async () => {
    const markdownRaw = debouncedSource();
    if (!markdownRaw) {
      setPreviewHtml("");
      return;
    }

    const requestId = ++renderRequestId;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10_000);
    onCleanup(() => {
      clearTimeout(timeoutId);
      controller.abort();
    });

    const markdownBody = markdownRaw.replace(/^---\s*\n[\s\S]*?\n---\s*\n/, "");
    void (async () => {
      try {
        const res = await fetch("/api/markdown/render", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ markdown: markdownBody }),
          signal: controller.signal,
        });
        if (!res.ok) {
          throw new Error(`Markdown render failed: ${res.status}`);
        }

        const data = (await res.json()) as { html: string };
        // avoid covered by old data
        if (requestId === renderRequestId) {
          setPreviewHtml(data.html);
        }
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") {
          return;
        }
        if (requestId === renderRequestId) {
          console.error(e);
        }
      }
    })();
  });

  // sync solid & hidden textarea state
  createEffect(() => {
    props.textarea.value = source();
  });

  // inject katex CSS into global head for `@font-face` support inside shadow DOM
  createEffect(() => {
    if (!document.head.querySelector(`link[href="${katexCssUrl}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = katexCssUrl;
      document.head.appendChild(link);
    }
  });

  // prevent css pollution, use shadow DOM
  createEffect(() => {
    if (previewContainerRef) {
      let shadow = previewContainerRef.shadowRoot;
      if (!shadow) {
        // do not merge with HTML content update
        shadow = previewContainerRef.attachShadow({ mode: "open" });
        shadow.innerHTML = `
          <link rel="stylesheet" href="${tailwindCssUrl}" />
          <link rel="stylesheet" href="${markdownCssUrl}" />
          <link rel="stylesheet" href="${katexCssUrl}" />
          <div id="content-container"></div>
        `;
      }

      // update content
      const container = shadow.getElementById("content-container");
      if (container) {
        cleanup(container);
        container.className = isDark() ? "dark" : "";
        container.innerHTML = `
          <div class="markdown-body is-decorated">
            ${previewHtml()}
          </div>
        `;
        bootstrap(container);
        onCleanup(() => cleanup(container));
      }
    }
  });

  const handleInput = (e: InputEvent & { currentTarget: HTMLTextAreaElement; target: Element }) => {
    setSource(e.currentTarget.value);
  };

  const handleKeyDown = (e: KeyboardEvent & { currentTarget: HTMLTextAreaElement }) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      const form = props.textarea.closest("form");
      form?.submit();
    }
  };

  return (
    <div
      style={{
        "--font-sans": '"LXGW WenKai", sans-serif',
        "--font-mono": '"Maple Mono Normal", monospace',
        display: "flex",
        "flex-wrap": "wrap",
        gap: "1rem",
        width: "100%",
      }}
    >
      {/* left. input area */}
      <textarea
        style={{
          flex: "1 1 32rem",
          height: "max(50vh, 600px)",
          padding: "1rem",
          border: "1px solid",
          "border-color": isDark() ? "#444c56" : "#d1d5db",
          "border-radius": "0.5rem",
          resize: "none",
          outline: "none",
          // it not a bug, mono font only in editor
          "font-family": "var(--font-mono)",
          "box-sizing": "border-box",
          "background-color": isDark() ? "#0d1117" : "#ffffff",
          color: isDark() ? "#e6edf3" : "#000000",
          "min-width": "min(100%, 32rem)",
          "font-size": "18px",
        }}
        value={source()}
        onInput={handleInput}
        onKeyDown={handleKeyDown}
      ></textarea>

      {/* right. preview area */}
      <div
        style={{
          flex: "1 1 32rem",
          height: "max(50vh, 600px)",
          padding: "1rem",
          border: "1px solid #d1d5db",
          "border-radius": "0.5rem",
          "overflow-y": "auto",
          "background-color": isDark() ? "#1a1c25" : "#f8fafc",
          "box-sizing": "border-box",
          position: "relative",
          "min-width": "min(100%, 32rem)",
        }}
      >
        <button
          onClick={(e) => {
            e.preventDefault();
            setIsDark(!isDark());
          }}
          style={{
            position: "absolute",
            top: "0.5rem",
            right: "0.5rem",
            padding: "0.25rem 0.5rem",
            cursor: "pointer",
            "border-radius": "0.25rem",
            border: "1px solid",
            "border-color": isDark() ? "#444c56" : "#d1d5db",
            background: isDark() ? "#24292f" : "#ffffff",
            color: isDark() ? "#e6edf3" : "#24292f",
            "font-size": "0.8rem",
            "z-index": 10,
          }}
        >
          {isDark() ? "Light Mode" : "Dark Mode"}
        </button>
        <div ref={(el) => (previewContainerRef = el)}></div>
      </div>
    </div>
  );
}
