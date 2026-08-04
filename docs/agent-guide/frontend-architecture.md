# Frontend Architecture

This project is not a single SPA. Django server-renders pages, a protocol-driven navigation layer (HTMX and Native Navigation API adapters, chosen per deployment mode) handles client-side page swapping, Solid powers on-demand interactive islands, and Vite builds both client and SSR assets. Each layer has a distinct responsibility; Solid is not the default layer for frontend work.

## Invariants

- Main content, reading flows, and basic navigation work with JavaScript disabled.
- Django templates are the source of page content and SEO semantics; JavaScript enhances them.
- Page responses carry a navigation protocol (`app-build-id`, `app-navigation-version`) and a `page-navigation-mode` meta tag. The `body` keeps `hx-boost` with the `app-page-lifecycle` extension, so a visit may be a full page load or a client-side swap; a swap is only performed when the page protocol matches, otherwise the browser reloads.
- Solid islands are small and self-contained; an entire page, article body, or basic navigation is not rendered as an island.
- `web/static/dist/` and `web/static/ssr/` contain generated assets. They are not edited manually and their filenames are not hard-coded in templates.

## Directory ownership

| Location                                 | Owns                                                                  |
| ---------------------------------------- | --------------------------------------------------------------------- |
| `web/urls.py`, `web/views.py`            | Page routes, server-side data, and template responses                 |
| `web/templates/web/layout/base.html`     | Site shell, Vite entries, navigation protocol meta tags, HTMX wiring  |
| `web/templates/web/pages/`               | Server-rendered page bodies                                           |
| `web/templates/web/partials/`            | Reusable template fragments (navigation, footer, etc.)                |
| `web/typescript/core/behaviors/`         | Small framework-free DOM enhancements                                 |
| `web/typescript/core/navigation/`        | Navigation protocol, app page events, HTMX and native adapters        |
| `web/typescript/core/htmx.ts`            | HTMX setup module: extensions, history cache, CSRF                    |
| `web/typescript/core/page-transition.ts` | Page transition timing and `data-page-transition` toggling            |
| `web/typescript/core/bootstrap.tsx`      | Island mount/hydrate runtime and lifecycle wiring                     |
| `web/typescript/core/lazy-islands.ts`    | On-demand Solid runtime loading (keeps Solid out of the first bundle) |
| `web/typescript/islands/`                | Self-contained Solid interaction components                           |
| `web/typescript/ssr.tsx`                 | SSR build entry: island manifest and hydration script                 |
| `web/typescript/admin/`                  | Django admin frontend enhancements                                    |
| `web/typescript/styles/`                 | CSS entries composed by `vite.config.mts`                             |
| `web/context_processors.py`              | Navigation protocol meta values (`APP_BUILD_ID`, mode, version)       |
| `api/markdown/post_processors.py`        | Safe article HTML post-processing and Markdown directives             |
| `vite.config.mts`                        | Vite entries, development server, and client/SSR builds               |

## Page rendering and interaction lifecycle

The initial request follows this path:

```text
Browser request
  -> web/urls.py / web/views.py
  -> Django template (usually extending web/layout/base.html)
  -> Readable server-rendered HTML
  -> web/typescript/index.tsx
     -> setupNavigation()   // pick the native or HTMX adapter from page-navigation-mode
     -> setupBehaviors()    // behavior runtime on app page events
     -> setupLazyIsland()   // load the Solid runtime only when [data-solid-island] exists
```

`base.html` loads the theme script early, then the frontend entry. HTMX is not loaded up front: it is imported dynamically by the navigation setup only when the page runs in an HTMX-supported mode. An ordinary template does not need a separate JavaScript entry point.

All client-side navigation reports through the app page events defined in `core/navigation/events.ts`:

```text
navigation request
  -> app:navigation-start
  -> app:before-swap: clean up mounted islands, destroy behaviors, start leave transition
  -> body swap (innerHTML replacement)
  -> app:after-swap: behavior runtime remounts, lazy islands scan and mount, start enter transition
  -> app:navigation-end (or app:navigation-error with a phase)
```

The HTMX adapter implements this lifecycle as an `app-page-lifecycle` HTMX extension; the native adapter targets the same events. Behavior code does not assume it runs only once, and it does not directly mutate DOM owned by a Solid island.

## Layer responsibilities

| Need                                                                | Layer                                        | Why                                                             |
| ------------------------------------------------------------------- | -------------------------------------------- | --------------------------------------------------------------- |
| A new page, article list, article body, or basic link               | Django view and template                     | Keeps it readable, indexable, and functional without JavaScript |
| A click that replaces content, pagination, or a form response       | Django template fragment and HTMX            | Preserves server rendering and avoids unnecessary client state  |
| Image zoom, code expansion, or another enhancement to existing HTML | `core/behaviors/`                            | Does not need framework state and remounts after page swaps     |
| A chart, REPL, counter, or complex local state                      | `islands/`                                   | Limits client runtime and state to a small area                 |
| An interactive directive in a Markdown article                      | `api/markdown/post_processors.py` and island | Requires an explicit mapping and HTML allowlist protection      |
| The post editor in Django admin                                     | `typescript/admin/`                          | Keeps admin lifecycle separate from public-page code            |

Features that must convey information or support a basic task without JavaScript are server-rendered; HTMX, behaviors, and islands layer on top as enhancements.

## Navigation protocol

Page responses carry three meta tags emitted by `base.html` from `web/context_processors.py`:

- `app-build-id` and `app-navigation-version` identify the deployed frontend build. `core/navigation/protocol.ts` compares them before every swap; a mismatch forces a full page reload (fallback), and the HTMX history cache generation is reset when the build changes.
- `page-navigation-mode` is `auto` (default), `native`, or `htmx`, driven by `PAGE_NAVIGATION_MODE` in settings. `core/navigation/setup.ts` reads it and decides which adapter to load:
    - `auto`: use the native adapter when the Navigation API is available, otherwise the HTMX adapter.
    - `native`: require the Navigation API; the HTMX adapter is never loaded.
    - `htmx`: always use the HTMX adapter.
    - If no adapter applies, links fall through to normal full-page loads.

`core/htmx.ts` is the HTMX setup module, loaded dynamically only for HTMX modes. It imports `htmx.org` plus the `head-support` and `preload` extensions, installs the `app-page-lifecycle` extension, syncs the HTMX history cache, attaches the CSRF header from the `csrftoken` cookie, and exposes `window.htmx`. The `body` declares `hx-boost="true"` and `hx-ext="head-support, preload, app-page-lifecycle"`.

The HTMX adapter (`core/navigation/htmx-adapter.ts`) treats a boosted body swap as a navigation transaction: it starts the request, guards the response protocol, applies a page transition, emits the app events, and finishes with an outcome (`completed` / `cancelled` / `fallback`). Errors map to a phase (`request` / `validation` / `swap` / `settle`).

`core/navigation/page.ts` (renamed from `fetch-page.ts`) and `head.ts` back the native adapter. Fetched pages are validated before swapping (same-origin, status, content type, `Content-Disposition`, `body.site-body`, a single `<title>`, and the dynamic-head markers), and any mismatch becomes a full reload with a reason (`cross-origin` / `status` / `content-type` / `content-disposition` / `invalid-html` / `protocol`). `route-policy.ts` decides which URLs and sources are eligible, and `native-adapter.ts` intercepts `navigate` events: it fetches and validates the page, prepares the head (stylesheet preload, commit/rollback), and swaps the body children. For push and replace navigations, browsers with precommit redirect support commit and swap an eligible same-origin redirect's final URL without a second request. Unsupported browsers, history traversals that redirect, excluded final URLs, and validation or swap failures fall back to a full navigation.

### Dynamic head

`base.html` marks a dynamic head region between the `app-dynamic-head-start` and `app-dynamic-head-end` meta tags; page templates extend it via the `extra_head` and `seo_head` blocks. `core/navigation/head.ts` reads the region, and `hasValidPageHead()` (single title, `body.site-body`, valid dynamic-head range) is one of the swap preconditions.

## Behaviors

A behavior is a small enhancement to existing server-rendered HTML. Behavior modules live under `web/typescript/core/behaviors/`, are registered in `core/behaviors/index.ts`, and each returns a `Behavior`. The behavior runtime (`core/behaviors/runtime.ts`) handles initial mounting and `app:after-swap` remounting; there is no parallel global HTMX lifecycle inside an individual behavior.

Behavior contract:

- `mount(root, context)` queries only `root` and its descendants; `queryAllIncludingRoot()` is available when needed.
- Mounting is idempotent: repeated `app:after-swap` events do not wrap a node or add listeners twice.
- Listeners are registered with `context.signal`; `destroy()` owns global state, temporary DOM, or timers.
- Behavior code does not process nodes inside `[data-solid-island]`.

## Solid islands

Islands handle interaction that cannot be expressed clearly as a small DOM behavior. The client registry is `web/typescript/islands/index.ts` and uses dynamic imports so that Solid and every island stay out of the initial bundle. `core/lazy-islands.ts` scans the page for `[data-solid-island]` and only then loads `core/bootstrap.tsx` plus the registry; `core/bootstrap.tsx` (`setupIslands`) mounts or hydrates islands, cleans them up on `app:before-swap`, and re-bootstraps on `app:after-swap`.

A server-rendered island container carries `data-solid-island` (component name), `data-props` (JSON), and, when SSR output is present, `data-solid-ssr`. Bootstrap hydrates `data-solid-ssr` containers and falls back to client rendering (CSR) if hydration throws; plain containers are always rendered client-side.

### SSR islands in templates

An island rendered in an ordinary Django template lives under `web/typescript/islands/<Name>/` and is exported as the default component. It is registered on the client in `web/typescript/islands/index.ts` and for the server in `web/typescript/islands/ssr_registry.ts`, with safe `placeholderProps` where needed. The Django template loads `solid_islands` and renders it with `{% solid_island "Name" key=value %}`.

In development, `solid_island` emits a client-side placeholder container. In production, it reads the SSR manifest and emits HTML that can hydrate. A component registered only on the client cannot be used by this template tag in production.

Current islands: `Counter`, `PythonREPL`, `Chart`, and `WIP`. Only `Counter` and `WIP` are registered in `ssr_registry.ts`; `PythonREPL` and `Chart` depend on browser APIs and are client-only, so they cannot be used with `{% solid_island %}` in production.

### Markdown directive islands

Article directives are explicitly mapped by `MARKDOWN_DIRECTIVE_ISLANDS` in `api/markdown/post_processors.py` to `data-solid-island` and `data-props`. Current mappings: `counter` → `Counter`, `python-wasm` / `python-repl` → `PythonREPL`, `chart` / `charts` → `Chart`. These islands mount on the client and suit components that depend on browser APIs.

Mappings are intentional named mappings only; arbitrary component names are never accepted. The required tag and `data-*` attributes stay within the HTML sanitization allowlist (`span` and `div` allow `data-solid-island` and `data-props`). Post-processing and `nh3` sanitization rules are part of the security boundary, so attributes from article content are not trusted.

## Styles, assets, and builds

- Shared style entries live in `web/typescript/styles/`, are declared in `vite.config.mts`, and are loaded with template tags. `globals.css` is the main entry: it imports Tailwind CSS and composes `base.css`, `navbar.css`, and `footer.css`. `font.css` bundles the web fonts, and the article-specific `markdown.css` is loaded only by `blog_post.html`.
- Each independent Vite entry has a declaration in `vite.config.mts` and a Django template that loads it. Client entries are `index` (`web/typescript/index.tsx`), `loadTheme` (`core/theme.ts`), `globalCss`, `fontCss`, `markdownCss`, and `admin`; the SSR build has its own entry, `ssr` (`web/typescript/ssr.tsx`).
- `core/theme.ts` runs early to prevent a theme flash; it is not folded into the ordinary frontend entry.
- `vite.config.mts` uses rolldown inputs, Tailwind CSS v4, `vite-plugin-solid`, a Django-template HMR plugin, and `sonda` for bundle analysis (`ANALYZE=1 pnpm build`).
- Static assets are served via `{% vite_asset '...' %}` (after loading `vite`): the tag points at the Vite development server in development and resolves the build manifest in production.
- Client and SSR island behavior is production-validated with `pnpm build:all` (client build → SSR build → `collectstatic`). The SSR build runs `scripts/build_ssr_assets.mjs`, which writes `solid-islands.json` (read by the `solid_island` template tag) and `solid-hydrate-script.js` (loaded by `base.html`).

## Development and verification

Frontend tests stay next to the code they exercise and use the narrowest runtime that can verify the behavior.

| Pattern                                  | Runtime            | Responsibility                                                   |
| ---------------------------------------- | ------------------ | ---------------------------------------------------------------- |
| `web/typescript/**/*.test.ts(x)`         | Vitest with jsdom  | Logic, Solid component behavior, and small DOM enhancements      |
| `web/typescript/**/*.browser.test.ts(x)` | Vitest Browser     | Canvas, pointer events, layout, and other real browser APIs      |
| `web/tests/test_*.py`                    | Django test runner | Views, template tags, middleware, and server-rendering contracts |
| `web/e2e/*.spec.ts`                      | Playwright         | HTMX and native navigation, and critical browser journeys        |
| `web/e2e/ssr/*.ssr.spec.ts`              | Playwright         | Built SSR output and real hydration                              |
| `web/typescript/test/`                   | Shared test code   | Reusable setup and fixtures; no test cases                       |

Vitest runs in two projects defined by `vite.config.mts`: a jsdom `unit` project and a `browser` project (Playwright provider, firefox and chromium) that only picks up `*.browser.test.ts(x)` files.

Generated SSR markup is not hand-copied, and Solid hydration markers are not asserted. Device and viewport selection lives in Playwright projects so each E2E test runs only in the environments it needs.

Development commands:

```bash
pnpm dev
uv run manage.py runasgi
```

Checks:

```bash
pnpm test
pnpm test:unit
pnpm test:browser
pnpm test:e2e
pnpm test:e2e:native
pnpm test:ssr
pnpm typecheck
pnpm lint
pnpm build:all
uv run manage.py test web.tests
uv run manage.py test api.tests.test_markdown_post_process
```
