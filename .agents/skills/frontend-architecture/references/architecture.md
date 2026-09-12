# Frontend Architecture Reference

## System model and invariants

This is not a single SPA. Django renders pages, a protocol-driven navigation layer selects an HTMX or Native Navigation API adapter per deployment mode, Solid powers on-demand interactive islands, and Vite builds client and SSR assets.

The shared frontend invariants are in [web/AGENTS.md](../../../../web/AGENTS.md). The sections below describe implementation details for the relevant integration.

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
| `api/markdown/markdown_it.py` | Python integration with the native Markdown renderer |
| `api/markdown/islands.py` | Loading the built music placeholder |
| `native/markdown/src/solid_island.rs` | Allowed directive components and props, island rewriting, and music placeholder insertion |
| `native/markdown/src/sanitizer.rs` | Markdown HTML sanitization |
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

Template islands must be registered in both the client registry and `web/typescript/islands/ssr_registry.ts`, then rendered with `{% solid_island "Name" key=value %}`. Supply safe placeholder props for components that need them during SSR generation. Client-only islands cannot use this tag in production. `Counter` and `WIP` support hydration; `PythonREPL`, `Chart`, and `MusicDock` are client-only. `MusicTrack` is registered separately in `STATIC_COMPONENTS`: Solid renders its initial state inside `NoHydration` into the manifest's `staticIslands` section. Python supplies this trusted build output to the native Markdown renderer, which inserts it after sanitizing user HTML. The wrapper has no `data-solid-ssr`, so the client replaces the placeholder. Keep music styles in the initial Markdown CSS bundle to reserve space before JavaScript loads.

Markdown directives are intentional named mappings in `native/markdown/src/solid_island.rs` (`Component::from_directive`). Current mappings are `counter` to `Counter`, `python-wasm` and `python-repl` to `PythonREPL`, `python-playground` to `PythonPlayground`, `chart` and `charts` to `Chart`, and `music` to `MusicTrack`, which only forwards its `src`. Never accept arbitrary component names. Keep required elements and `data-*` attributes aligned with the sanitizer allowlist in `native/markdown/src/sanitizer.rs`, and keep directive URLs within the origins the CSP allows (music playback and metadata need them under `media-src` and `connect-src`).

## Styles, assets, and builds

Shared style entries live in `web/typescript/styles/` and are declared in `vite.config.mts`. `globals.css` composes Tailwind, base, navbar, and footer styles; `font.css` bundles fonts; `markdown.css` is article-specific. Load entries with `{% vite_asset %}`. Keep the early `core/theme.ts` entry separate to prevent theme flash. The `dark:` variant is bound to the `.dark` class by the `@custom-variant` in `globals.css`, matching the server-rendered `<html class="dark">` and `core/theme.ts`; dropping it falls back to `prefers-color-scheme` and light-preference visitors lose the dark-theme styles. Body copy uses `--font-sans` (LXGW WenKai Screen), but small UI text (spoiler summaries, the music cards and dock) uses `font-family: system-ui, sans-serif` because the kai face is hard to read at small sizes.

The client entries are `index`, `loadTheme`, `globalCss`, `fontCss`, `markdownCss`, and `admin`; SSR uses `ssr`. `pnpm build:all` builds the client and SSR assets and runs `collectstatic`. SSR generation writes `solid-islands.json` and `solid-hydrate-script.js`. Run `pnpm build:ssr` before rendering Markdown or running its Python tests and the music placeholder browser tests, including in development. Rebuild after changing the card's initial markup; stored article HTML needs regeneration to pick up the new placeholder.

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

Choose checks according to the changed behavior:

- TypeScript logic and DOM behavior: focused tests through `pnpm test:unit`; use `pnpm test:browser` for real browser APIs and `pnpm typecheck` for TypeScript changes.
- Django views, templates, and Markdown integration: focused test labels under `web.tests` or `api.tests.test_markdown_post_process`, using `uv run manage.py test <test_label>`.
- Native Markdown directives or sanitization: relevant Rust tests in `native/markdown`, plus Python integration coverage when rendered output changes.
- Navigation: the affected adapter suite (`pnpm test:e2e:htmx` or `pnpm test:e2e:native`). For shared navigation changes, exercise both adapters; `pnpm test:e2e:base:htmx` and `pnpm test:e2e:base:native` run shared journeys against each adapter. `pnpm test:e2e` runs the base journeys with the configured mode.
- Template island output or hydration: `pnpm test:ssr`, which already builds SSR assets and runs Django island tests and browser hydration coverage.
- Build configuration, manifests, or static asset integration: `pnpm build:all`, which builds client and SSR assets and runs `collectstatic`. Use `pnpm build` or `pnpm build:ssr` when only that output needs verification.

Reuse current build outputs where the selected check permits it. Avoid rerunning a build already covered by a successful check unless inputs changed or another check requires it.
