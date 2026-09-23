# Frontend Architecture Reference

## System model

This is not a single SPA. Django renders pages, a protocol-driven navigation layer selects an HTMX or Native Navigation API adapter per deployment mode, Solid powers on-demand interactive islands, and Vite builds client and SSR assets.

The frontend invariants are listed in [web/AGENTS.md](../../../../web/AGENTS.md). The sections below describe the implementation details behind those invariants.

`web/static/dist/` and `web/static/ssr/` contain generated build output; source files never reference these directories or their filenames.

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

Failures emit `app:navigation-error` with a phase. Before a swap, islands are cleaned up, behaviors destroyed, and the leave transition started. After it, behaviors and islands remount and the enter transition starts.

`page-navigation-mode` is `auto`, `native`, or `htmx`. Auto prefers the Navigation API and falls back to HTMX. Native requires that API. HTMX always loads the HTMX adapter. If no adapter applies, normal full-page navigation remains available.

`core/navigation/policy/route-policy.ts` is the single source of URL and source eligibility (reserved prefixes, feed, Markdown, and non-HTML routes excluded). Both adapters validate the page protocol. The native adapter additionally validates origin, status, content type, content disposition, `body.site-body`, a single title, and dynamic-head markers. Validation or swap failures use full navigation.

The dynamic head lies between `app-dynamic-head-start` and `app-dynamic-head-end` in `base.html`; templates extend it through `extra_head` and `seo_head`.

## Behaviors

Behaviors are registered in `core/behaviors/index.ts`. Their `mount(root, context)` runs on the initial document and again after every swap, so mounting is idempotent. Behaviors query only their root and descendants, register listeners with `context.signal`, and release global state, temporary DOM, and timers in `destroy()`. Nodes inside `[data-solid-island]` belong to Solid islands and are not processed by behaviors.

## Solid islands and SSR

The client registry is `web/typescript/islands/index.ts`, with dynamic imports keeping Solid and island code out of the first bundle. `core/lazy-islands.ts` scans for `[data-solid-island]` before loading the runtime. Containers use `data-solid-island`, JSON `data-props`, and optionally `data-solid-ssr`. SSR containers hydrate; hydration failure falls back to client rendering.

Template islands are registered in both the client registry and `web/typescript/islands/ssr_registry.ts`, and rendered with `{% solid_island "Name" key=value %}`. SSR generation supplies safe placeholder props for components that need them. Client-only islands cannot use this tag in production. `Counter` and `WIP` support hydration; `PythonREPL`, `Chart`, and `MusicDock` are client-only. `MusicTrack` is registered separately in `STATIC_COMPONENTS`: Solid renders its initial state inside `NoHydration` into the manifest's `staticIslands` section. Python supplies this trusted build output to the native Markdown renderer, which inserts it after sanitizing user HTML. The wrapper has no `data-solid-ssr`, so the client replaces the placeholder rather than hydrating it. Music styles stay in the initial Markdown CSS bundle to reserve space before JavaScript loads.

Markdown directives are a fixed set of named mappings in `native/markdown/src/solid_island.rs` (`Component::from_directive`): `counter` to `Counter`, `python-wasm` and `python-repl` to `PythonREPL`, `python-playground` to `PythonPlayground`, `chart` and `charts` to `Chart`, and `music` to `MusicTrack`, which only forwards its `src`. Component names are never taken from user input. Required elements and `data-*` attributes stay within the sanitizer allowlist in `native/markdown/src/sanitizer.rs`, and directive URLs stay within the origins the CSP allows (music playback and metadata need them under `media-src` and `connect-src`).

## Styles, assets, and builds

Shared style entries live in `web/typescript/styles/` and are declared in `vite.config.mts`. `globals.css` composes Tailwind, base, navbar, and footer styles; `font.css` bundles fonts; `markdown.css` is article-specific. Templates load entries with `{% vite_asset %}`. The early `core/theme.ts` entry is separate to prevent theme flash. The `dark:` variant is bound to the `.dark` class by the `@custom-variant` in `globals.css`, matching the server-rendered `<html class="dark">` and `core/theme.ts`; without it, styles fall back to `prefers-color-scheme` and light-preference visitors lose the dark-theme styles. Body copy uses `--font-sans` (LXGW WenKai Screen); small UI text (spoiler summaries, the music cards and dock) uses `font-family: system-ui, sans-serif` because the kai face is hard to read at small sizes.

The client entries are `index`, `loadTheme`, `globalCss`, `fontCss`, `markdownCss`, and `admin`; SSR uses `ssr`. `pnpm build:all` builds the client and SSR assets and runs `collectstatic`. SSR generation writes `solid-islands.json` and `solid-hydrate-script.js`. Markdown rendering, its Python tests, and the music placeholder browser tests consume the SSR build output. The card's initial markup is embedded in stored article HTML, so regenerated build output requires regenerating stored articles.
