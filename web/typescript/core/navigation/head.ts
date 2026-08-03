const HEAD_START_SELECTOR = 'meta[name="app-dynamic-head-start"]';
const HEAD_END_SELECTOR = 'meta[name="app-dynamic-head-end"]';
const DEFAULT_STYLESHEET_TIMEOUT_MS = 4_000;

interface DynamicHeadRange {
  readonly start: HTMLMetaElement;
  readonly end: HTMLMetaElement;
  readonly nodes: Node[];
}

interface PageHeadSnapshot {
  readonly document: Document;
  readonly url: URL;
  readonly title: string;
  readonly range: DynamicHeadRange;
}

export interface PreparedPageHead {
  commit(): void;
  rollback(): void;
}

export interface PreparePageHeadOptions {
  readonly signal: AbortSignal;
  readonly currentUrl: URL;
  readonly nextUrl: URL;
  readonly stylesheetTimeoutMs?: number;
}

interface PreparedStylesheets {
  readonly bindings: ReadonlyMap<HTMLLinkElement, HTMLLinkElement>;
  readonly inserted: readonly HTMLLinkElement[];
}

interface PrepareStylesheetsOptions {
  readonly signal: AbortSignal;
  readonly timeoutMs: number;
}

type PageHeadTransactionState = "prepared" | "committed" | "rolled-back";

export class PageHeadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PageHeadError";
  }
}

// --- helper method ---

function isStylesheet(node: Node): node is HTMLLinkElement {
  if (node.nodeType !== node.ELEMENT_NODE) {
    return false;
  }

  const element = node as Element;
  return (
    element.tagName === "LINK" &&
    element.getAttribute("rel")?.toLowerCase().split(/\s+/).includes("stylesheet") === true &&
    element.hasAttribute("href")
  );
}

function isExecutableScript(node: Node): boolean {
  if (node.nodeType !== node.ELEMENT_NODE) {
    return false;
  }

  const element = node as Element;
  return (
    element.tagName === "SCRIPT" &&
    (element.getAttribute("type") ?? "").trim().toLowerCase() !== "application/ld+json"
  );
}

function stylesheetKey(link: HTMLLinkElement, baseUrl: URL): string {
  return JSON.stringify([
    new URL(link.getAttribute("href")!, baseUrl).href,
    link.getAttribute("media") ?? "",
    link.getAttribute("type") ?? "",
    link.getAttribute("integrity") ?? "",
    link.getAttribute("crossorigin") ?? "",
    link.getAttribute("referrerpolicy") ?? "",
    link.hasAttribute("disabled"),
  ]);
}

function waitForStylesheet(
  link: HTMLLinkElement,
  timeoutMs: number,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let timeout: ReturnType<typeof setTimeout>;

    const cleanup = () => {
      clearTimeout(timeout);
      link.removeEventListener("load", loaded);
      link.removeEventListener("error", failed);
      signal.removeEventListener("abort", aborted);
    };

    const loaded = () => {
      cleanup();
      resolve();
    };

    const failed = () => {
      cleanup();
      reject(new PageHeadError(`Failed to load stylesheet: ${link.href}`));
    };

    const aborted = () => {
      cleanup();
      reject(signal.reason);
    };

    link.addEventListener("load", loaded, { once: true });
    link.addEventListener("error", failed, { once: true });
    signal.addEventListener("abort", aborted, { once: true });

    timeout = setTimeout(() => {
      cleanup();
      reject(new PageHeadError(`Stylesheet timed out: ${link.href}`));
    }, timeoutMs);

    if (signal.aborted) {
      aborted();
    }
  });
}

function indexStylesheets(page: PageHeadSnapshot): Map<string, HTMLLinkElement[]> {
  const stylesheets = new Map<string, HTMLLinkElement[]>();
  for (const node of page.range.nodes) {
    if (!isStylesheet(node)) {
      continue;
    }

    const key = stylesheetKey(node, page.url);
    const matches = stylesheets.get(key) ?? [];
    matches.push(node);
    stylesheets.set(key, matches);
  }

  return stylesheets;
}

function removeNodes(nodes: readonly Node[]): void {
  for (const node of nodes) {
    node.parentNode?.removeChild(node);
  }
}

function readDynamicHeadRange(document: Document): DynamicHeadRange | null {
  const starts = document.head.querySelectorAll<HTMLMetaElement>(HEAD_START_SELECTOR);
  const ends = document.head.querySelectorAll<HTMLMetaElement>(HEAD_END_SELECTOR);
  // reject not standard structure
  if (starts.length !== 1 || ends.length !== 1) {
    return null;
  }

  const start = starts[0];
  const end = ends[0];
  if (start.parentNode !== document.head || end.parentNode !== document.head) {
    return null;
  }

  // it must can be parsed
  let current: Node | null = start.nextSibling;
  const nodes: Node[] = [];
  while (current && current !== end) {
    nodes.push(current);
    current = current.nextSibling;
  }
  if (current !== end) {
    return null;
  }

  return {
    start,
    end,
    nodes,
  };
}

function hasValidPageContract(document: Document): boolean {
  return (
    document.body.matches("body.site-body") && document.head.querySelectorAll("title").length === 1
  );
}

function readPageHead(document: Document, url: URL): PageHeadSnapshot | null {
  const range = readDynamicHeadRange(document);
  if (!range) {
    return null;
  }

  return {
    document,
    url: new URL(url),
    title: document.title,
    range,
  };
}

function readValidPageHead(document: Document, url: URL): PageHeadSnapshot | null {
  if (!hasValidPageContract(document)) {
    return null;
  }

  return readPageHead(document, url);
}

export function hasValidPageHead(document: Document): boolean {
  return hasValidPageContract(document) && readDynamicHeadRange(document) !== null;
}

// --- core method ---

async function prepareStylesheets(
  current: PageHeadSnapshot,
  next: PageHeadSnapshot,
  options: PrepareStylesheetsOptions,
): Promise<PreparedStylesheets> {
  const existing = indexStylesheets(current);
  const usage = new Map<string, number>();
  const bindings = new Map<HTMLLinkElement, HTMLLinkElement>();
  const inserted: HTMLLinkElement[] = [];
  const loadTasks: Promise<void>[] = [];

  for (const node of next.range.nodes) {
    if (!isStylesheet(node)) {
      continue;
    }

    const key = stylesheetKey(node, next.url);
    const index = usage.get(key) ?? 0;
    usage.set(key, index + 1);

    let liveStylesheet = existing.get(key)?.[index];
    // if not a live stylesheet node. load it
    if (!liveStylesheet) {
      liveStylesheet = current.document.importNode(node, true);
      liveStylesheet.href = new URL(node.getAttribute("href")!, next.url).href;
      inserted.push(liveStylesheet);
      loadTasks.push(waitForStylesheet(liveStylesheet, options.timeoutMs, options.signal));
      current.range.end.before(liveStylesheet); // add to document to tell browser load this
    }

    bindings.set(node, liveStylesheet);
  }

  // wait until finish (avoid FOUC)
  try {
    await Promise.all(loadTasks);
    options.signal.throwIfAborted();
  } catch (e) {
    removeNodes(inserted);
    throw e;
  }

  return { bindings, inserted };
}

function materializeHeadNodes(
  current: PageHeadSnapshot,
  next: PageHeadSnapshot,
  stylesheets: PreparedStylesheets,
): Node[] {
  const desiredNodes: Node[] = [];
  for (const node of next.range.nodes) {
    // this project not accept executable script in dynamic head
    if (isExecutableScript(node)) {
      continue;
    }

    if (!isStylesheet(node)) {
      desiredNodes.push(current.document.importNode(node, true));
      continue;
    }

    const stylesheet = stylesheets.bindings.get(node);
    if (!stylesheet) {
      const href = new URL(node.getAttribute("href")!, next.url).href;
      throw new PageHeadError(`Prepared stylesheet is missing: ${href}`);
    }

    desiredNodes.push(stylesheet);
  }

  return desiredNodes;
}

function createPageHeadTransaction(
  current: PageHeadSnapshot,
  next: PageHeadSnapshot,
  stylesheets: PreparedStylesheets,
): PreparedPageHead {
  let state: PageHeadTransactionState = "prepared";

  const rollback = () => {
    if (state !== "prepared") {
      return;
    }

    state = "rolled-back";
    removeNodes(stylesheets.inserted);
  };

  const commit = () => {
    if (state !== "prepared") {
      return;
    }

    const live = readDynamicHeadRange(current.document);
    if (!live || live.start !== current.range.start || live.end !== current.range.end) {
      rollback();
      throw new PageHeadError("Dynamic head changed before commit");
    }

    let desiredNodes: Node[];
    try {
      desiredNodes = materializeHeadNodes(current, next, stylesheets);
    } catch (error) {
      rollback();
      throw error;
    }

    removeNodes(live.nodes);
    live.end.before(...desiredNodes);
    current.document.title = next.title;
    state = "committed";
  };

  return { commit, rollback };
}

export async function preparePageHead(
  currentDocument: Document,
  nextDocument: Document,
  options: PreparePageHeadOptions,
): Promise<PreparedPageHead> {
  const current = readPageHead(currentDocument, options.currentUrl);
  const next = readValidPageHead(nextDocument, options.nextUrl);
  if (!current || !next) {
    throw new PageHeadError("Invalid dynamic head contract");
  }

  const stylesheets = await prepareStylesheets(current, next, {
    signal: options.signal,
    timeoutMs: options.stylesheetTimeoutMs ?? DEFAULT_STYLESHEET_TIMEOUT_MS,
  });
  return createPageHeadTransaction(current, next, stylesheets);
}
