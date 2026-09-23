import type { ModelViewerElement } from "@google/model-viewer";
import { createSignal, onCleanup, onMount, Show } from "solid-js";

interface Props {
  src?: unknown;
  alt?: unknown;
}

let runtimePromise: Promise<void> | undefined;
const DEFAULT_MODEL_SRC = "https://static.gsgfs.moe/blog/creeper.glb";

function loadRuntime(): Promise<void> {
  runtimePromise ??= import("@google/model-viewer")
    .then(() => undefined)
    .catch((e) => {
      runtimePromise = undefined;
      throw e;
    });
  return runtimePromise;
}

function modelSource(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) {
    return DEFAULT_MODEL_SRC;
  }

  try {
    const url = new URL(value, document.baseURI);
    return ["http:", "https:"].includes(url.protocol) ? url.href : DEFAULT_MODEL_SRC;
  } catch {
    return DEFAULT_MODEL_SRC;
  }
}

export default function ModelViewer(props: Readonly<Props>) {
  let container: HTMLDivElement;
  let observer: IntersectionObserver | undefined;
  let viewer: ModelViewerElement | undefined;
  let listeners: AbortController | undefined;
  let disposed = false;
  let loading = false;

  const [status, setStatus] = createSignal("Scroll here to load the model");
  const [failed, setFailed] = createSignal(false);

  function removeViewer() {
    listeners?.abort();
    listeners = undefined;
    viewer?.remove();
    viewer = undefined;
  }

  async function load(src = modelSource(props.src)) {
    if (disposed || loading || viewer) {
      return;
    }

    loading = true;
    setFailed(false);
    setStatus("Loading...");

    try {
      await loadRuntime();

      if (disposed || !container.isConnected) {
        return;
      }

      const element = document.createElement("model-viewer");
      viewer = element;
      listeners = new AbortController();

      element.setAttribute("camera-controls", "");
      // avoid can't scroll on small screen
      element.setAttribute("touch-action", "pan-y");
      element.setAttribute("loading", "eager");
      element.style.cssText = "display:block;width:100%;height:100%";
      element.alt =
        src === DEFAULT_MODEL_SRC
          ? "Creeper 3D model"
          : typeof props.alt === "string"
            ? props.alt
            : "3D model";

      element.addEventListener(
        "load",
        () => {
          if (disposed || viewer !== element) {
            return;
          }

          setStatus("");
        },
        {
          signal: listeners.signal,
        },
      );

      element.addEventListener(
        "error",
        () => {
          if (disposed || viewer !== element) {
            return;
          }

          removeViewer();
          if (src !== DEFAULT_MODEL_SRC) {
            loading = false;
            void load(DEFAULT_MODEL_SRC);
            return;
          }

          setFailed(true);
          setStatus("Model load failed");
        },
        {
          signal: listeners.signal,
        },
      );

      element.src = src;
      container.append(element);
    } catch (e) {
      if (disposed) {
        return;
      }

      removeViewer();
      setFailed(true);
      setStatus(e instanceof Error ? e.message : "Model load failed");
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    if (!("IntersectionObserver" in window)) {
      void load();
      return;
    }

    observer = new IntersectionObserver(
      (entries) => {
        if (disposed || !entries.some((entry) => entry.isIntersecting)) {
          return;
        }

        observer?.disconnect();
        void load();
      },
      {
        rootMargin: "200px",
      },
    );

    observer.observe(container);
  });

  onCleanup(() => {
    disposed = true;
    observer?.disconnect();
    removeViewer();
  });

  return (
    <div class="model-viewer-stage">
      <div
        class="model-viewer-stage"
        ref={(e) => (container = e)}
        aria-busy={Boolean(status()) && !failed()}
      />

      <Show when={status()}>
        <span class="model-viewer-status" role="status">
          {status()}
        </span>
      </Show>
    </div>
  );
}
