# Frontend Architecture Reference

## System model and invariants

This is not a single SPA. Django renders pages, a protocol-driven navigation layer selects an HTMX or Native Navigation API adapter per deployment mode, Solid powers on-demand interactive islands, and Vite builds client and SSR assets.

- Main content, reading flows, and basic navigation must work without JavaScript.
- Django templates own page content and SEO semantics; JavaScript enhances them.
- Page responses expose `app-build-id`, `app-navigation-version`, and `page-navigation-mode`. A client-side swap is allowed only when the protocol matches; otherwise reload the page.
- Keep Solid islands small and self-contained.
- Never edit `web/static/dist/` or `web/static/ssr/`, and never hard-code their filenames.

## Ownership map

| Location | Responsibility |
| --- | --- |
| `web/urls.py`, `web/views/` | Page routes, server data, and template responses |
| `web/templates/web/layout/base.html` | Shell, Vite entries, protocol metadata, and HTMX wiring |
| `web/templates/web/pages/` | Server-rendered page bodies |
| `web/templates/web/partials/` | Reusable template fragments |
| `web/typescript/core/behaviors/` | Framework-free DOM enhancements |
| `web/typescript/core/navigation/` | Navigation facade, contracts, policy, runtime, and adapters |
| `web/typescript/core/bootstrap.tsx` | Island mount/hydrate runtime and lifecycle wiring |
| `web/typescript/core/lazy-islands.ts` | On-demand Solid runtime loading |
| `web/typescript/islands/` | Self-contained Solid components |
| `web/typescript/ssr.tsx` | SSR manifest and hydration-script entry |
| `web/typescript/admin/` | Django admin enhancements |
| `web/typescript/styles/` | CSS entries composed by Vite |
| `web/context_processors.py` | Navigation build ID, mode, and version |
| `api/markdown/post_processors.py` | Safe article post-processing and directive mappings |
| `vite.config.mts` | Development server and client/SSR builds |

## Rendering and navigation lifecycle

The initial request flows from `web/urls.py` and `web/views/`, through a Django template extending `base.html`, to readable HTML. `web/typescript/index.tsx` then calls `setupNavigation()`, `setupBehaviors()`, and `setupLazyIsland()`. HTMX and Solid load dynamically only when their modes or markup require them.

All adapters report through the same events:

```text
app:navigation-start
  -> app:before-swap
  -> body swap
  -> app:after-swap
  -> app:navigation-end
```

Failures emit `app:navigation-error` with a phase. Before a swap, clean up islands, destroy behaviors, and start the leave transition. After it, remount behaviors and islands and start the enter transition.

`page-navigation-mode` is `auto`, `native`, or `htmx`. Auto prefers the Navigation API and falls back to HTMX. Native requires that API. HTMX always loads the HTMX adapter. If no adapter applies, normal full-page navigation remains available.

`core/navigation/policy/route-policy.ts` centrally owns URL and source eligibility. Do not duplicate its exclusions. Both adapters validate the page protocol. The native adapter additionally validates origin, status, content type, content disposition, `body.site-body`, a single title, and dynamic-head markers. Validation or swap failures use full navigation.

The dynamic head lies between `app-dynamic-head-start` and `app-dynamic-head-end` in `base.html`; templates extend it through `extra_head` and `seo_head`.

## Behaviors

Register behaviors in `core/behaviors/index.ts`. Their `mount(root, context)` may run initially and after every swap, so mounting must be idempotent. Query only the root and descendants, use `queryAllIncludingRoot()` when necessary, register listeners with `context.signal`, and use `destroy()` for global state, temporary DOM, or timers. Never process nodes inside `[data-solid-island]`.

## Solid islands and SSR

The client registry is `web/typescript/islands/index.ts`; use dynamic imports so Solid and island code stay out of the first bundle. `core/lazy-islands.ts` scans for `[data-solid-island]` before loading the runtime. Containers use `data-solid-island`, JSON `data-props`, and optionally `data-solid-ssr`. Hydrate SSR containers and fall back to client rendering if hydration fails.

Template islands must be registered in both the client registry and `web/typescript/islands/ssr_registry.ts`, then rendered with `{% solid_island "Name" key=value %}`. Client-only islands cannot use this tag in production. `Counter` and `WIP` support SSR; `PythonREPL` and `Chart` depend on browser APIs and are client-only.

Markdown directives are intentional named mappings in `MARKDOWN_DIRECTIVE_ISLANDS`. Current mappings are `counter` to `Counter`, `python-wasm` and `python-repl` to `PythonREPL`, and `chart` and `charts` to `Chart`. Never accept arbitrary component names. Keep required elements and `data-*` attributes aligned with the `nh3` sanitizer allowlist.

## Styles, assets, and builds

Shared style entries live in `web/typescript/styles/` and are declared in `vite.config.mts`. `globals.css` composes Tailwind, base, navbar, and footer styles; `font.css` bundles fonts; `markdown.css` is article-specific. Load entries with `{% vite_asset %}`. Keep the early `core/theme.ts` entry separate to prevent theme flash.

The client entries are `index`, `loadTheme`, `globalCss`, `fontCss`, `markdownCss`, and `admin`; SSR uses `ssr`. `pnpm build:all` builds the client and SSR assets and runs `collectstatic`. SSR generation writes `solid-islands.json` and `solid-hydrate-script.js`.

## Test selection

| Pattern | Runtime and scope |
| --- | --- |
| `web/typescript/**/*.test.ts(x)` | Vitest/jsdom for logic and DOM behavior |
| `web/typescript/**/*.browser.test.ts(x)` | Vitest Browser for real browser APIs |
| `web/tests/test_*.py` | Django rendering and server contracts |
| `web/e2e/base/*.spec.ts` | Adapter-independent journeys |
| `web/e2e/htmx/*.spec.ts` | HTMX adapter behavior |
| `web/e2e/native/*.spec.ts` | Native adapter behavior |
| `web/e2e/ssr/*.ssr.spec.ts` | Built SSR output and hydration |

Use `pnpm test`, `pnpm test:unit`, `pnpm test:browser`, `pnpm test:e2e`, `pnpm test:e2e:htmx`, `pnpm test:e2e:native`, `pnpm test:e2e:base:htmx`, `pnpm test:e2e:base:native`, `pnpm test:ssr`, `pnpm typecheck`, `pnpm lint`, and `pnpm build:all` as appropriate. For server coverage, use `uv run manage.py test web.tests` and `uv run manage.py test api.tests.test_markdown_post_process`.
