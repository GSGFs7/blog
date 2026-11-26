import { cleanup as cleanupRender, fireEvent, render, waitFor } from "@solidjs/testing-library";
import { flush } from "solid-js";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const bootstrapMocks = vi.hoisted(() => ({
  bootstrap: vi.fn(),
  cleanup: vi.fn(),
}));

vi.mock("@/core/bootstrap", () => ({
  bootstrap: bootstrapMocks.bootstrap,
  cleanup: bootstrapMocks.cleanup,
}));

import { AdminPostEditor } from "./AdminPostEditor";

interface CreateTextareaOptions {
  value?: string;
  katexCssUrl?: string;
  markdownCssUrl?: string;
  tailwindCssUrl?: string;
  inForm?: boolean;
}

function createSourceTextarea(options: CreateTextareaOptions = {}): {
  textarea: HTMLTextAreaElement;
  form?: HTMLFormElement;
} {
  const textarea = document.createElement("textarea");
  textarea.value = options.value ?? "";
  if (options.katexCssUrl !== undefined) {
    textarea.dataset.katexCssUrl = options.katexCssUrl;
  }
  if (options.markdownCssUrl !== undefined) {
    textarea.dataset.markdownCssUrl = options.markdownCssUrl;
  }
  if (options.tailwindCssUrl !== undefined) {
    textarea.dataset.tailwindCssUrl = options.tailwindCssUrl;
  }

  if (options.inForm) {
    const form = document.createElement("form");
    form.appendChild(textarea);
    document.body.appendChild(form);
    return { textarea, form };
  }

  document.body.appendChild(textarea);
  return { textarea };
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function getPreviewShadow(container: HTMLElement): ShadowRoot {
  const previewWrapper = container.firstElementChild?.lastElementChild as HTMLElement;
  const previewHost = previewWrapper.lastElementChild as HTMLElement;
  expect(previewHost.shadowRoot).not.toBeNull();
  return previewHost.shadowRoot!;
}

function getEditorTextarea(container: HTMLElement): HTMLTextAreaElement {
  return container.querySelector("textarea")!;
}

function getModeButton(container: HTMLElement): HTMLButtonElement {
  return container.querySelector("button")!;
}

beforeEach(() => {
  bootstrapMocks.bootstrap.mockReset();
  bootstrapMocks.cleanup.mockReset();
});

afterEach(() => {
  cleanupRender();
  document.body.innerHTML = "";
  for (const link of document.head.querySelectorAll('link[rel="stylesheet"]')) {
    link.remove();
  }
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("initializes shadow DOM CSS links, dark container, and deduplicated head KaTeX link when empty", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const { textarea: firstTextarea } = createSourceTextarea({
    tailwindCssUrl: "/static/tailwind.css",
    markdownCssUrl: "/static/markdown.css",
    katexCssUrl: "/static/custom-katex.css",
  });

  const first = render(() => <AdminPostEditor textarea={firstTextarea} />);
  flush();

  expect(fetchMock).not.toHaveBeenCalled();

  const shadow = getPreviewShadow(first.container);
  const hrefs = Array.from(shadow.querySelectorAll('link[rel="stylesheet"]')).map((el) =>
    el.getAttribute("href"),
  );
  expect(hrefs).toEqual([
    "/static/tailwind.css",
    "/static/markdown.css",
    "/static/custom-katex.css",
  ]);
  expect(shadow.getElementById("content-container")).toHaveClass("dark");

  expect(document.head.querySelectorAll('link[href="/static/custom-katex.css"]')).toHaveLength(1);

  const { textarea: secondTextarea } = createSourceTextarea({
    katexCssUrl: "/static/custom-katex.css",
  });
  render(() => <AdminPostEditor textarea={secondTextarea} />);
  flush();

  expect(document.head.querySelectorAll('link[href="/static/custom-katex.css"]')).toHaveLength(1);
});

test("falls back to default KaTeX CSS URL when dataset.katexCssUrl is omitted", () => {
  vi.stubGlobal("fetch", vi.fn());
  const { textarea } = createSourceTextarea();

  const { container } = render(() => <AdminPostEditor textarea={textarea} />);
  flush();

  const shadow = getPreviewShadow(container);
  const links = Array.from(shadow.querySelectorAll('link[rel="stylesheet"]'));
  expect(links[2]).toHaveAttribute("href", "/static/katex/katex.min.css");
  expect(document.head.querySelector('link[href="/static/katex/katex.min.css"]')).not.toBeNull();
});

test("renders initial markdown with frontmatter stripped and invokes bootstrap lifecycle", async () => {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ html: "<h1>Hello</h1>" }),
  }));
  vi.stubGlobal("fetch", fetchMock);

  const { textarea } = createSourceTextarea({
    value: "---\ntitle: Demo\n---\n# Hello\n",
  });

  const { container } = render(() => <AdminPostEditor textarea={textarea} />);

  await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/markdown/render",
    expect.objectContaining({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: "# Hello\n" }),
      signal: expect.any(AbortSignal),
    }),
  );

  const shadow = getPreviewShadow(container);
  const contentContainer = shadow.getElementById("content-container")!;
  await waitFor(() => {
    expect(contentContainer.querySelector(".markdown-body.is-decorated")?.innerHTML).toContain(
      "<h1>Hello</h1>",
    );
  });

  expect(bootstrapMocks.cleanup).toHaveBeenCalledWith(contentContainer);
  expect(bootstrapMocks.bootstrap).toHaveBeenCalledWith(contentContainer);
});

test("debounces markdown rendering by 300ms while syncing hidden textarea immediately", async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ html: "<p>ab</p>" }),
  }));
  vi.stubGlobal("fetch", fetchMock);

  const { textarea } = createSourceTextarea();
  const { container } = render(() => <AdminPostEditor textarea={textarea} />);
  flush();

  const editorTextarea = getEditorTextarea(container);
  fireEvent.input(editorTextarea, { target: { value: "a" } });
  flush();
  expect(textarea.value).toBe("a");

  await vi.advanceTimersByTimeAsync(200);
  expect(fetchMock).not.toHaveBeenCalled();

  fireEvent.input(editorTextarea, { target: { value: "ab" } });
  flush();
  expect(textarea.value).toBe("ab");

  await vi.advanceTimersByTimeAsync(299);
  expect(fetchMock).not.toHaveBeenCalled();

  await vi.advanceTimersByTimeAsync(1);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/markdown/render",
    expect.objectContaining({
      body: JSON.stringify({ markdown: "ab" }),
    }),
  );

  const contentContainer = getPreviewShadow(container).getElementById("content-container")!;
  expect(contentContainer.innerHTML).toContain("<p>ab</p>");

  fireEvent.input(editorTextarea, { target: { value: "" } });
  flush();
  await vi.advanceTimersByTimeAsync(300);

  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(contentContainer.querySelector(".markdown-body")?.innerHTML.trim()).toBe("");
});

test("aborts superseded requests and ignores out-of-order stale responses", async () => {
  vi.useFakeTimers();
  const firstResponse = createDeferred<{
    ok: boolean;
    status: number;
    json: () => Promise<{ html: string }>;
  }>();
  const secondResponse = createDeferred<{
    ok: boolean;
    status: number;
    json: () => Promise<{ html: string }>;
  }>();
  const signals: AbortSignal[] = [];

  const fetchMock = vi
    .fn()
    .mockImplementationOnce((_url: string, init: RequestInit) => {
      signals.push(init.signal!);
      return firstResponse.promise;
    })
    .mockImplementationOnce((_url: string, init: RequestInit) => {
      signals.push(init.signal!);
      return secondResponse.promise;
    });
  vi.stubGlobal("fetch", fetchMock);

  const { textarea } = createSourceTextarea();
  const { container } = render(() => <AdminPostEditor textarea={textarea} />);
  flush();

  const editorTextarea = getEditorTextarea(container);
  fireEvent.input(editorTextarea, { target: { value: "first" } });
  flush();
  await vi.advanceTimersByTimeAsync(300);

  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(signals[0].aborted).toBe(false);

  fireEvent.input(editorTextarea, { target: { value: "second" } });
  flush();
  await vi.advanceTimersByTimeAsync(300);

  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(signals[0].aborted).toBe(true);
  expect(signals[1].aborted).toBe(false);

  secondResponse.resolve({
    ok: true,
    status: 200,
    json: async () => ({ html: "<p>newer</p>" }),
  });
  await Promise.resolve();
  await Promise.resolve();
  flush();

  const contentContainer = getPreviewShadow(container).getElementById("content-container")!;
  expect(contentContainer.innerHTML).toContain("<p>newer</p>");

  firstResponse.resolve({
    ok: true,
    status: 200,
    json: async () => ({ html: "<p>stale</p>" }),
  });
  await Promise.resolve();
  await Promise.resolve();
  flush();

  expect(contentContainer.innerHTML).toContain("<p>newer</p>");
  expect(contentContainer.innerHTML).not.toContain("<p>stale</p>");
});

test("logs non-2xx errors, ignores AbortError, and aborts after 10s timeout", async () => {
  vi.useFakeTimers();
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const hangingDeferred = createDeferred<never>();
  const signals: AbortSignal[] = [];

  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ html: "<p>initial</p>" }),
    })
    .mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ html: "" }),
    })
    .mockRejectedValueOnce(new DOMException("Aborted", "AbortError"))
    .mockImplementationOnce((_url: string, init: RequestInit) => {
      signals.push(init.signal!);
      return hangingDeferred.promise;
    });
  vi.stubGlobal("fetch", fetchMock);

  const { textarea } = createSourceTextarea({ value: "initial" });
  const { container } = render(() => <AdminPostEditor textarea={textarea} />);
  await vi.advanceTimersByTimeAsync(0);

  const contentContainer = getPreviewShadow(container).getElementById("content-container")!;
  expect(contentContainer.innerHTML).toContain("<p>initial</p>");

  const editorTextarea = getEditorTextarea(container);
  fireEvent.input(editorTextarea, { target: { value: "server error" } });
  flush();
  await vi.advanceTimersByTimeAsync(300);

  expect(consoleError).toHaveBeenCalledOnce();
  expect(contentContainer.innerHTML).toContain("<p>initial</p>");

  consoleError.mockClear();
  fireEvent.input(editorTextarea, { target: { value: "aborted" } });
  flush();
  await vi.advanceTimersByTimeAsync(300);

  expect(consoleError).not.toHaveBeenCalled();

  fireEvent.input(editorTextarea, { target: { value: "timeout" } });
  flush();
  await vi.advanceTimersByTimeAsync(300);
  expect(signals[0].aborted).toBe(false);

  await vi.advanceTimersByTimeAsync(10_000);
  expect(signals[0].aborted).toBe(true);
});

test("toggles dark and light mode without submitting enclosing form", () => {
  vi.stubGlobal("fetch", vi.fn());
  const { textarea, form } = createSourceTextarea({ inForm: true });
  const submitSpy = vi.spyOn(form!, "submit").mockImplementation(() => undefined);

  const { container } = render(() => <AdminPostEditor textarea={textarea} />);
  flush();

  const button = getModeButton(container);
  const editorTextarea = getEditorTextarea(container);
  const contentContainer = getPreviewShadow(container).getElementById("content-container")!;

  expect(button).toHaveTextContent("Light Mode");
  expect(contentContainer.className).toBe("dark");
  expect(editorTextarea.style.backgroundColor).toBe("rgb(13, 17, 23)");

  const clickToLight = new MouseEvent("click", { bubbles: true, cancelable: true });
  button.dispatchEvent(clickToLight);
  flush();

  expect(clickToLight.defaultPrevented).toBe(true);
  expect(submitSpy).not.toHaveBeenCalled();
  expect(button).toHaveTextContent("Dark Mode");
  expect(contentContainer.className).toBe("");
  expect(editorTextarea.style.backgroundColor).toBe("rgb(255, 255, 255)");

  button.click();
  flush();

  expect(button).toHaveTextContent("Light Mode");
  expect(contentContainer.className).toBe("dark");
});

test("handles Ctrl+S and Cmd+S submission shortcuts", () => {
  vi.stubGlobal("fetch", vi.fn());
  const { textarea, form } = createSourceTextarea({ inForm: true });
  const submitSpy = vi.spyOn(form!, "submit").mockImplementation(() => undefined);

  const { container } = render(() => <AdminPostEditor textarea={textarea} />);
  flush();

  const editorTextarea = getEditorTextarea(container);

  const plainS = new KeyboardEvent("keydown", { key: "s", bubbles: true, cancelable: true });
  editorTextarea.dispatchEvent(plainS);
  expect(plainS.defaultPrevented).toBe(false);
  expect(submitSpy).not.toHaveBeenCalled();

  const ctrlA = new KeyboardEvent("keydown", {
    key: "a",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
  });
  editorTextarea.dispatchEvent(ctrlA);
  expect(ctrlA.defaultPrevented).toBe(false);
  expect(submitSpy).not.toHaveBeenCalled();

  const ctrlS = new KeyboardEvent("keydown", {
    key: "s",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
  });
  editorTextarea.dispatchEvent(ctrlS);
  expect(ctrlS.defaultPrevented).toBe(true);
  expect(submitSpy).toHaveBeenCalledTimes(1);

  const metaS = new KeyboardEvent("keydown", {
    key: "s",
    metaKey: true,
    bubbles: true,
    cancelable: true,
  });
  editorTextarea.dispatchEvent(metaS);
  expect(metaS.defaultPrevented).toBe(true);
  expect(submitSpy).toHaveBeenCalledTimes(2);

  const { textarea: standaloneTextarea } = createSourceTextarea({ inForm: false });
  const standalone = render(() => <AdminPostEditor textarea={standaloneTextarea} />);
  flush();
  const standaloneCtrlS = new KeyboardEvent("keydown", {
    key: "s",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
  });
  getEditorTextarea(standalone.container).dispatchEvent(standaloneCtrlS);
  expect(standaloneCtrlS.defaultPrevented).toBe(true);
});

test("aborts in-flight fetch and cleans up shadow content container on unmount", async () => {
  const deferred = createDeferred<{
    ok: boolean;
    status: number;
    json: () => Promise<{ html: string }>;
  }>();
  let capturedSignal: AbortSignal | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, init: RequestInit) => {
      capturedSignal = init.signal ?? undefined;
      return deferred.promise;
    }),
  );

  const { textarea } = createSourceTextarea({ value: "pending" });
  const { container, unmount } = render(() => <AdminPostEditor textarea={textarea} />);

  await waitFor(() => expect(capturedSignal).toBeDefined());
  const contentContainer = getPreviewShadow(container).getElementById("content-container")!;
  bootstrapMocks.cleanup.mockClear();

  expect(capturedSignal!.aborted).toBe(false);
  unmount();

  expect(capturedSignal!.aborted).toBe(true);
  expect(bootstrapMocks.cleanup).toHaveBeenCalledWith(contentContainer);
});
