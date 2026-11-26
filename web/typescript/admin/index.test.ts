import { afterEach, beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  setupIslands: vi.fn(),
  render: vi.fn(),
  adminPostEditor: vi.fn(() => null),
  components: { Counter: vi.fn() },
}));

vi.mock("@/core/bootstrap", () => ({
  setupIslands: mocks.setupIslands,
}));

vi.mock("@/islands", () => ({
  COMPONENTS: mocks.components,
}));

vi.mock("@solidjs/web", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@solidjs/web")>()),
  render: mocks.render,
}));

vi.mock("./PostEditor", () => ({
  AdminPostEditor: mocks.adminPostEditor,
}));

beforeEach(() => {
  vi.resetModules();
  mocks.setupIslands.mockReset();
  mocks.render.mockReset();
  mocks.adminPostEditor.mockClear();
  document.body.innerHTML = "";
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

test("sets up islands and skips mounting editor when no matching textarea exists", async () => {
  document.body.innerHTML =
    '<textarea class="solid-markdown-editor" data-editor-target="summary"></textarea>';

  await import("./index");
  await Promise.resolve();

  expect(mocks.setupIslands).toHaveBeenCalledWith(mocks.components);
  expect(mocks.render).not.toHaveBeenCalled();
  expect(document.body.children).toHaveLength(1);
});

test("mounts AdminPostEditor before and hides the target content textarea", async () => {
  document.body.innerHTML = `
    <div class="field-row">
      <textarea class="solid-markdown-editor" data-editor-target="content">hello</textarea>
    </div>
  `;
  const textarea = document.querySelector<HTMLTextAreaElement>(
    '.solid-markdown-editor[data-editor-target="content"]',
  )!;

  await import("./index");
  await vi.waitFor(() => expect(mocks.render).toHaveBeenCalledOnce());

  expect(mocks.setupIslands).toHaveBeenCalledWith(mocks.components);
  expect(textarea.style.display).toBe("none");

  const wrapper = textarea.previousElementSibling as HTMLElement;
  expect(wrapper).toBeInstanceOf(HTMLDivElement);
  expect(wrapper).toHaveStyle({ flex: "1 1 0", minWidth: "0" });

  const [renderFn, mountTarget] = mocks.render.mock.calls[0] as [() => unknown, HTMLElement];
  expect(mountTarget).toBe(wrapper);

  renderFn();
  expect(mocks.adminPostEditor).toHaveBeenCalledWith({ textarea });
});
