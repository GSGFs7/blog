import { expect, test, vi } from "vitest";

import {
  page,
  PageLoadError,
  type FetchPageOptions,
  type PageLoadResult,
  type PageReloadReason,
} from "./page";
import type { PageProtocol } from "./protocol";

const ORIGIN = "https://example.com";
const PROTOCOL: PageProtocol = {
  navigationVersion: "1",
  buildId: "test-build",
};

function pageHtml(protocol: PageProtocol = PROTOCOL): string {
  return `<!doctype html>
    <html>
      <head>
        <meta name="app-navigation-version" content="${protocol.navigationVersion}">
        <meta name="app-build-id" content="${protocol.buildId}">
        <title>Test Page</title>
        <meta name="app-dynamic-head-start">
        <meta name="description" content="page description">
        <meta name="app-dynamic-head-end">
      </head>
      <body class="site-body"></body>
    </html>`;
}

interface Harness {
  readonly controller: AbortController;
  readonly fetchImpl: ReturnType<typeof vi.fn>;
  readonly options: FetchPageOptions;
}

function harness(): Harness {
  const controller = new AbortController();
  const fetchImpl = vi.fn();
  return {
    controller,
    fetchImpl,
    options: {
      signal: controller.signal,
      expectedOrigin: ORIGIN,
      currentProtocol: PROTOCOL,
      fetchImpl,
    },
  };
}

function htmlResponse(html: string | null, init: ResponseInit = {}, url = ""): Response {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "text/html");
  }
  const response = new Response(html, { ...init, headers });
  Object.defineProperty(response, "url", { value: url });
  return response;
}

function expectReload(result: PageLoadResult, reason: PageReloadReason, href: string): void {
  expect(result.kind).toBe("reload");
  if (result.kind !== "reload") {
    return;
  }
  expect(result.reason).toBe(reason);
  expect(result.url.href).toBe(href);
}

test.each([
  ["a different origin", "https://attacker.example/page"],
  ["a non-http(s) protocol", "javascript:void(0)"],
  ["a data URL", "data:text/html,hello"],
])("reloads the browser for %s without fetching", async (_name, raw) => {
  const { fetchImpl, options } = harness();

  const result = await page(new URL(raw), options);

  expectReload(result, "cross-origin", new URL(raw).href);
  expect(fetchImpl).not.toHaveBeenCalled();
});

test("requests the URL without the fragment", async () => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(htmlResponse(pageHtml()));

  await page(new URL("https://example.com/post/1#comment-3"), options);

  expect(fetchImpl).toHaveBeenCalledTimes(1);
  const [url, init] = fetchImpl.mock.calls[0];
  expect((url as URL).href).toBe("https://example.com/post/1");
  expect(init).toMatchObject({
    method: "GET",
    credentials: "same-origin",
    redirect: "follow",
  });
  expect(init.headers).toMatchObject({ Accept: "text/html" });
  expect(init.signal).toBe(options.signal);
});

test("swaps a valid same-origin page and keeps the fragment", async () => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(htmlResponse(pageHtml()));

  const result = await page(new URL("https://example.com/post/1#comment-3"), options);

  expect(result.kind).toBe("swap");
  if (result.kind !== "swap") {
    return;
  }
  expect(result.page.requestedUrl.href).toBe("https://example.com/post/1#comment-3");
  expect(result.page.finalUrl.href).toBe("https://example.com/post/1#comment-3");
  expect(result.page.document.querySelector("title")?.textContent).toBe("Test Page");
  expect(result.page.response.status).toBe(200);
  expect(result.page.deliverySource).toBe("origin");
});

test("follows same-origin redirects and keeps the fragment", async () => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(htmlResponse(pageHtml(), {}, "https://example.com/redirected/path"));

  const result = await page(new URL("https://example.com/start#top"), options);

  expect(result.kind).toBe("swap");
  if (result.kind !== "swap") {
    return;
  }
  expect(result.page.finalUrl.href).toBe("https://example.com/redirected/path#top");
});

test("accepts a content type with parameters", async () => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(
    htmlResponse(pageHtml(), { headers: { "Content-Type": "text/html; charset=utf-8" } }),
  );

  const result = await page(new URL("https://example.com/"), options);

  expect(result.kind).toBe("swap");
});

test("uses an injected parser", async () => {
  const { fetchImpl, options } = harness();
  const document = new DOMParser().parseFromString(pageHtml(), "text/html");
  const parseHtml = vi.fn(() => document);
  fetchImpl.mockResolvedValue(htmlResponse(pageHtml()));

  const result = await page(new URL("https://example.com/"), { ...options, parseHtml });

  expect(parseHtml).toHaveBeenCalledWith(expect.stringContaining("app-navigation-version"));
  expect(result.kind).toBe("swap");
  if (result.kind !== "swap") {
    return;
  }
  expect(result.page.document).toBe(document);
});

const reloadCases: Array<[string, Response, PageReloadReason]> = [
  [
    "a cross-origin redirect",
    htmlResponse(pageHtml(), {}, "https://evil.example/x"),
    "cross-origin",
  ],
  ["a 404 response", htmlResponse(pageHtml(), { status: 404 }), "status"],
  ["a 500 response", htmlResponse(pageHtml(), { status: 500 }), "status"],
  ["a 204 response", htmlResponse(null, { status: 204 }), "status"],
  [
    "a non-html content type",
    htmlResponse("{}", { headers: { "Content-Type": "application/json" } }),
    "content-type",
  ],
  [
    "an attachment disposition",
    htmlResponse(pageHtml(), {
      headers: { "Content-Disposition": 'attachment; filename="report.pdf"' },
    }),
    "content-disposition",
  ],
];

test.each(reloadCases)("reloads the browser for %s", async (_name, response, reason) => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(response);

  const result = await page(new URL("https://example.com/page#frag"), options);

  expectReload(result, reason, "https://example.com/page#frag");
});

test("reloads when the page has no title", async () => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(htmlResponse(pageHtml().replace("<title>Test Page</title>", "")));

  const result = await page(new URL("https://example.com/"), options);

  expectReload(result, "invalid-html", "https://example.com/");
});

test("reloads when the body is not marked as a site body", async () => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(
    htmlResponse(pageHtml().replace('<body class="site-body">', "<body>")),
  );

  const result = await page(new URL("https://example.com/"), options);

  expectReload(result, "invalid-html", "https://example.com/");
});

test("reloads when the dynamic head range is missing", async () => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(
    htmlResponse(
      pageHtml()
        .replace('<meta name="app-dynamic-head-start">', "")
        .replace('<meta name="app-dynamic-head-end">', ""),
    ),
  );

  const result = await page(new URL("https://example.com/"), options);

  expectReload(result, "invalid-html", "https://example.com/");
});

test.each([
  ["a different build id", { ...PROTOCOL, buildId: "other-build" }],
  ["a different navigation version", { ...PROTOCOL, navigationVersion: "2" }],
])("reloads when the page protocol mismatches: %s", async (_name, pageProtocol) => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(htmlResponse(pageHtml(pageProtocol)));

  const result = await page(new URL("https://example.com/"), options);

  expectReload(result, "protocol", "https://example.com/");
});

test.each([
  ["origin", {}, "origin"],
  ["service-worker", { headers: { "X-Service-Worker-Cache": "hit" } }, "service-worker"],
  ["cloudflare", { headers: { "CF-Cache-Status": "HIT" } }, "cloudflare"],
])("reports %s as the delivery source", async (_name, init, expected) => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(htmlResponse(pageHtml(), init));

  const result = await page(new URL("https://example.com/"), options);

  expect(result.kind).toBe("swap");
  if (result.kind !== "swap") {
    return;
  }
  expect(result.page.deliverySource).toBe(expected);
});

test("rethrows the abort error when the request is aborted", async () => {
  const { controller, fetchImpl, options } = harness();
  controller.abort();
  fetchImpl.mockRejectedValue(new DOMException("The operation was aborted.", "AbortError"));

  const error = await page(new URL("https://example.com/"), options).catch((e) => e);

  expect(error).not.toBeInstanceOf(PageLoadError);
  expect((error as Error).name).toBe("AbortError");
});

test("rethrows when the signal aborts after the response resolves", async () => {
  const { controller, fetchImpl, options } = harness();
  fetchImpl.mockImplementation(async () => {
    controller.abort();
    return htmlResponse(pageHtml());
  });

  const error = await page(new URL("https://example.com/"), options).catch((e) => e);

  expect(error).not.toBeInstanceOf(PageLoadError);
  expect((error as Error).name).toBe("AbortError");
});

test("throws a request PageLoadError for network failures", async () => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockRejectedValue(new TypeError("Failed to fetch"));

  const error = await page(new URL("https://example.com/"), options).catch((e) => e);

  expect(error).toBeInstanceOf(PageLoadError);
  expect(error).toMatchObject({ phase: "request" });
});

test("throws a request PageLoadError when reading the body fails", async () => {
  const { fetchImpl, options } = harness();
  const response = {
    url: "",
    ok: true,
    status: 200,
    headers: new Headers({ "Content-Type": "text/html" }),
    text: vi.fn().mockRejectedValue(new TypeError("body stream error")),
  } as unknown as Response;
  fetchImpl.mockResolvedValue(response);

  const error = await page(new URL("https://example.com/"), options).catch((e) => e);

  expect(error).toBeInstanceOf(PageLoadError);
  expect(error).toMatchObject({ phase: "request" });
});

test("throws a validation PageLoadError when parsing fails", async () => {
  const { fetchImpl, options } = harness();
  fetchImpl.mockResolvedValue(htmlResponse(pageHtml()));
  const parseHtml = vi.fn(() => {
    throw new Error("broken parser");
  });

  const error = await page(new URL("https://example.com/"), {
    ...options,
    parseHtml,
  }).catch((e) => e);

  expect(error).toBeInstanceOf(PageLoadError);
  expect(error).toMatchObject({ phase: "validation" });
});
