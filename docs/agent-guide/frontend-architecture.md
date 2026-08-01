# Frontend Architecture

This project is not a single SPA. Django server-renders pages, HTMX progressively enhances navigation and partial replacement, Solid powers on-demand interactive islands, and Vite builds both client and SSR assets. Each layer has a distinct responsibility; Solid is not the default layer for frontend work.

## Invariants

- Main content, reading flows, and basic navigation work with JavaScript disabled.
- Django templates are the source of page content and SEO semantics; JavaScript enhances them.
- The `body` enables `hx-boost`, so a visit may be a full page load or an HTMX replacement.
- Solid islands are small and self-contained; an entire page, article body, or basic navigation is not rendered as an island.
- `web/static/dist/` and `web/static/ssr/` contain generated assets. They are not edited manually and their filenames are not hard-coded in templates.

## Directory ownership

| Location                              | Owns                                                      |
| ------------------------------------- | --------------------------------------------------------- |
| `web/urls.py`, `web/views.py`         | Page routes, server-side data, and template responses     |
| `web/templates/web/layout/base.html`  | Site shell, Vite entries, HTMX, and shared resources      |
| `web/templates/web/pages/`            | Server-rendered page bodies                               |
| `web/templates/web/partials/`         | Reusable template fragments (navigation, footer, etc.)    |
| `web/typescript/core/behaviors/`      | Small framework-free DOM enhancements                     |
| `web/typescript/islands/`             | Self-contained Solid interaction components               |
| `web/typescript/core/lazy-islands.ts` | On-demand Solid runtime loading                           |
| `web/typescript/admin/`               | Django admin frontend enhancements                        |
| `api/markdown/post_processors.py`     | Safe article HTML post-processing and Markdown directives |
| `vite.config.mts`                     | Vite entries, development server, and client/SSR builds   |

## Page rendering and interaction lifecycle

The initial request follows this path:

```text
Browser request
  -> web/urls.py / web/views.py
  -> Django template (usually extending web/layout/base.html)
  -> Readable server-rendered HTML
  -> web/typescript/index.tsx
     -> behaviors
     -> load the Solid island runtime only when [data-solid-island] exists
```

`base.html` loads the theme script early, then loads HTMX and the frontend entry. An ordinary template does not need a separate JavaScript entry point.

An HTMX navigation or replacement follows this path:

```text
HTMX request / DOM replacement
  -> htmx:load: behavior runtime remounts the affected subtree
  -> htmx:afterSwap: scan the new subtree and load or mount islands as needed
  -> htmx:beforeSwap: clean up mounted islands
```

Behavior code does not assume it runs only once, and it does not directly mutate DOM owned by a Solid island.

## Layer responsibilities

| Need                                                                | Layer                                     | Why                                                             |
| ------------------------------------------------------------------- | ----------------------------------------- | --------------------------------------------------------------- |
| A new page, article list, article body, or basic link               | Django view and template                  | Keeps it readable, indexable, and functional without JavaScript |
| A click that replaces content, pagination, or a form response       | Django template fragment and HTMX         | Preserves server rendering and avoids unnecessary client state  |
| Image zoom, code expansion, or another enhancement to existing HTML | `core/behaviors/`                         | Does not need framework state and remounts after HTMX changes   |
| A chart, REPL, counter, or complex local state                      | `islands/`                                | Limits client runtime and state to a small area                 |
| An interactive directive in a Markdown article                      | `api/markdown/post_processors.py` and island | Requires an explicit mapping and HTML allowlist protection    |
| The post editor in Django admin                                     | `typescript/admin/`                       | Keeps admin lifecycle separate from public-page code            |

Features that must convey information or support a basic task without JavaScript are server-rendered; HTMX, behaviors, and islands layer on top as enhancements.

## Behaviors

A behavior is a small enhancement to existing server-rendered HTML. Behavior modules live under `web/typescript/core/behaviors/`, are registered in `core/behaviors/index.ts`, and each returns a `Behavior`. The behavior runtime handles initial mounting and `htmx:load` subtree mounting; there is no parallel global HTMX lifecycle inside an individual behavior.

Behavior contract:

- `mount(root, context)` queries only `root` and its descendants; `queryAllIncludingRoot()` is available when needed.
- Mounting is idempotent: repeated `htmx:load` events do not wrap a node or add listeners twice.
- Listeners are registered with `context.signal`; `destroy()` owns global state, temporary DOM, or timers.
- Behavior code does not process nodes inside `[data-solid-island]`.

## Solid islands

Islands handle interaction that cannot be expressed clearly as a small DOM behavior. The client registry is `web/typescript/islands/index.ts` and uses dynamic imports so that Solid and every island stay out of the initial bundle.

### SSR islands in templates

An island rendered in an ordinary Django template lives under `web/typescript/islands/<Name>/` and is exported as the default component. It is registered on the client in `web/typescript/islands/index.ts` and for the server in `web/typescript/islands/ssr_registry.ts`, with safe `placeholderProps` where needed. The Django template loads `solid_islands` and renders it with `{% solid_island "Name" key=value %}`.

In development, `solid_island` emits a client-side placeholder container. In production, it reads the SSR manifest and emits HTML that can hydrate. A component registered only on the client cannot be used by this template tag in production.

### Markdown directive islands

Article directives are explicitly mapped by `MARKDOWN_DIRECTIVE_ISLANDS` in `api/markdown/post_processors.py` to `data-solid-island` and `data-props`. These islands mount on the client and suit components that depend on browser APIs.

Mappings are intentional named mappings only; arbitrary component names are never accepted. The required tag and `data-*` attributes stay within the HTML sanitization allowlist. Post-processing and `nh3` sanitization rules are part of the security boundary, so attributes from article content are not trusted.

## Styles, assets, and builds

- Shared style entries live in `web/typescript/styles/`, are declared in `vite.config.mts`, and are loaded with template tags.
- `globals.css`, `font.css`, and the article-specific `markdown.css` have separate responsibilities; each rule lives in the narrowest appropriate entry.
- Each independent Vite entry has a declaration in `vite.config.mts` and a Django template that loads it.
- `core/theme.ts` runs early to prevent a theme flash; it is not folded into the ordinary frontend entry.
- Static assets are served via `{% vite_asset '...' %}` (after loading `vite`): the tag points at the Vite development server in development and resolves the build manifest in production.
- Client and SSR island behavior is production-validated with `pnpm build:all`, which generates the Vite manifest, SSR island assets, and collected static files.

## Development and verification

Frontend tests stay next to the code they exercise and use the narrowest runtime that can verify the behavior.

| Pattern                                  | Runtime            | Responsibility                                                   |
| ---------------------------------------- | ------------------ | ---------------------------------------------------------------- |
| `web/typescript/**/*.test.ts(x)`         | Vitest with jsdom  | Logic, Solid component behavior, and small DOM enhancements      |
| `web/typescript/**/*.browser.test.ts(x)` | Vitest Browser     | Canvas, pointer events, layout, and other real browser APIs      |
| `web/tests/test_*.py`                    | Django test runner | Views, template tags, middleware, and server-rendering contracts |
| `web/e2e/*.spec.ts`                      | Playwright         | HTMX navigation and critical browser journeys                    |
| `web/e2e/ssr/*.ssr.spec.ts`              | Playwright         | Built SSR output and real hydration                              |
| `web/typescript/test/`                   | Shared test code   | Reusable setup and fixtures; no test cases                       |

Generated SSR markup is not hand-copied, and Solid hydration markers are not asserted. Device and viewport selection lives in Playwright projects so each E2E test runs only in the environments it needs.

Development commands:

```bash
pnpm dev
uv run manage.py runasgi
```

Checks:

```bash
pnpm test
pnpm test:e2e
pnpm test:ssr
pnpm typecheck
pnpm build:all
uv run manage.py test web.tests
uv run manage.py test api.tests.test_markdown_post_process
```
