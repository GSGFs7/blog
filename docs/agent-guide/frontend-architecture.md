# Frontend Architecture and Agent Guide

This project is not a single SPA. Django server-renders pages, HTMX progressively enhances navigation and partial replacement, Solid powers on-demand interactive islands, and Vite builds both client and SSR assets. Choose the correct layer before changing frontend code instead of defaulting to Solid.

## Invariants

- Main content, reading flows, and basic navigation must work with JavaScript disabled.
- Django templates are the source of page content and SEO semantics; JavaScript enhances them.
- The `body` enables `hx-boost`, so a visit may be a full page load or an HTMX replacement.
- Keep Solid islands small and self-contained. Do not move an entire page, article body, or basic navigation into an island.
- `web/static/dist/` and `web/static/ssr/` contain generated assets. Do not edit them manually or hard-code their filenames in templates.

## Directory ownership

| Location                              | Owns                                                      | Change it when                                                       |
| ------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------- |
| `web/urls.py`, `web/views.py`         | Page routes, server-side data, and template responses     | Adding a page or changing page data                                  |
| `web/templates/web/layout/base.html`  | Site shell, Vite entries, HTMX, and shared resources      | Changing the global page shell                                       |
| `web/templates/web/pages/`            | Server-rendered page bodies                               | Adding or changing readable page content                             |
| `web/templates/web/partials/`         | Reusable template fragments                               | Changing navigation, footer, or a partial template                   |
| `web/typescript/core/behaviors/`      | Small framework-free DOM enhancements                     | Adding progressive enhancements such as image zoom or code expansion |
| `web/typescript/islands/`             | Self-contained Solid interaction components               | Adding local state, complex interaction, or browser API use          |
| `web/typescript/core/lazy-islands.ts` | On-demand Solid runtime loading                           | Changing island loading behavior                                     |
| `web/typescript/admin/`               | Django admin frontend enhancements                        | Changing the post editor or other admin interaction                  |
| `api/markdown/post_processors.py`     | Safe article HTML post-processing and Markdown directives | Adding article directives, allowed attributes, or rendering rules    |
| `vite.config.mts`                     | Vite entries, development server, and client/SSR builds   | Adding an entry, build behavior, or Vite plugin                      |

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

Behavior code must not assume it runs only once, and it must not directly mutate DOM owned by a Solid island.

## Choose the implementation layer first

| Need                                                                | Preferred location                              | Why                                                             |
| ------------------------------------------------------------------- | ----------------------------------------------- | --------------------------------------------------------------- |
| A new page, article list, article body, or basic link               | Django view and template                        | Keeps it readable, indexable, and functional without JavaScript |
| A click that replaces content, pagination, or a form response       | Django template fragment and HTMX               | Preserves server rendering and avoids unnecessary client state  |
| Image zoom, code expansion, or another enhancement to existing HTML | `core/behaviors/`                               | Does not need framework state and remounts after HTMX changes   |
| A chart, REPL, counter, or complex local state                      | `islands/`                                      | Limits client runtime and state to a small area                 |
| An interactive directive in a Markdown article                      | `api/markdown/post_processors.py` and an island | Requires an explicit mapping and HTML allowlist protection      |
| The post editor in Django admin                                     | `typescript/admin/`                             | Keeps admin lifecycle separate from public-page code            |

If the feature must convey information or support a basic task without JavaScript, implement the server-rendered version first, then add HTMX, a behavior, or an island as enhancement.

## Adding a page

1. Add the view in `web/views.py` and register its route in `web/urls.py`.
2. Add a template under `web/templates/web/pages/` that extends `web/layout/base.html`.
3. Render readable content directly in the template; put page-specific metadata or styles in the appropriate block.
4. Add HTMX, a behavior, or an island only where enhancement is needed.
5. Add a Django test for the view or its important rendered output.

For a static asset, load `vite` and use `{% vite_asset '...' %}`. It points at the Vite development server in development and resolves the build manifest in production.

## Adding or changing a behavior

A behavior is a small enhancement to existing server-rendered HTML.

1. Create a module under `web/typescript/core/behaviors/` that returns a `Behavior`.
2. Register it in `core/behaviors/index.ts`.
3. In `mount(root, context)`, query only `root` and its descendants; `queryAllIncludingRoot()` is available when needed.
4. Make mounting idempotent: repeated `htmx:load` events must not wrap a node or add listeners twice.
5. Register listeners with `context.signal`; implement `destroy()` when the behavior owns global state, temporary DOM, or timers.
6. Do not process nodes inside `[data-solid-island]`.
7. Add or update a Vitest test for the behavior.

The existing behavior runtime handles initial mounting and `htmx:load` subtree mounting. Do not create a parallel global HTMX lifecycle inside an individual behavior.

## Adding or changing a Solid island

Use an island for interaction that cannot be expressed clearly as a small DOM behavior. The client registry is `web/typescript/islands/index.ts` and uses dynamic imports so that Solid and every island do not enter the initial bundle.

### SSR islands in templates

For an island rendered in an ordinary Django template:

1. Implement the component under `web/typescript/islands/<Name>/` and export it as the default component.
2. Register its client-side dynamic import in `web/typescript/islands/index.ts`.
3. Register the same component in `web/typescript/islands/ssr_registry.ts`, with safe `placeholderProps` if needed.
4. Load `solid_islands` in the Django template and render it with `{% solid_island "Name" key=value %}`.
5. Run the SSR build and test production rendering.

In development, `solid_island` emits a client-side placeholder container. In production, it reads the SSR manifest and emits HTML that can hydrate. A component registered only on the client cannot be used by this template tag in production.

### Markdown directive islands

Article directives are explicitly mapped by `MARKDOWN_DIRECTIVE_ISLANDS` in `api/markdown/post_processors.py` to `data-solid-island` and `data-props`. These islands mount on the client and suit components that depend on browser APIs.

When adding a directive:

1. Add only an intentional named mapping; never accept an arbitrary component name.
2. Ensure the required tag and `data-*` attributes remain in the HTML sanitization allowlist.
3. Register the component on the client.
4. Add tests for the conversion result and actual mounting.
5. If it later becomes an SSR template island, first verify that it runs in Node SSR, then add an SSR registration.

Do not trust attributes from article content. The post-processing and `nh3` sanitization rules are part of the security boundary.

## Styles, assets, and builds

- Shared style entries live in `web/typescript/styles/`, are declared in `vite.config.mts`, and are loaded with template tags.
- `globals.css`, `font.css`, and the article-specific `markdown.css` have separate responsibilities; put a rule in the narrowest appropriate entry.
- When adding an independent Vite entry, update both `vite.config.mts` and the Django template that loads it.
- `core/theme.ts` runs early to prevent a theme flash; do not fold it into the ordinary frontend entry.
- After changing client or SSR island behavior, production validation must include `pnpm build:all`; it generates the Vite manifest, SSR island assets, and collected static files.

## Development and verification

Common development commands:

```bash
pnpm dev
uv run manage.py runasgi
```

Choose checks that match the change:

```bash
pnpm test
pnpm typecheck
pnpm build:all
uv run manage.py test web.tests
uv run manage.py test api.tests.test_markdown_post_process
```

Before handing off a frontend change, confirm that:

- Main content and navigation still work with JavaScript disabled.
- A new behavior does not mount twice after an HTMX replacement, and a new island initializes correctly.
- A template island has both client and SSR registrations; a Markdown island has its directive and allowlist updates.
- No template directly references a fingerprinted build artifact.
- The applicable TypeScript, Django, and build checks pass.
