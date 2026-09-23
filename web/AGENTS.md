# Frontend Agent Guide

## No-JS baseline

- Keep main page content fully readable and basic navigation functional without JavaScript.
- Treat JavaScript as progressive enhancement. Interactive features such as comments and rich widgets do not need a no-JS implementation unless the task requires one.

## Non-negotiable rules

- Use Django templates for pages and content, the protocol-driven navigation layer (`core/navigation/`: HTMX or Native Navigation API adapter) for page swaps, behaviors for small DOM enhancements, and Solid islands for isolated stateful interaction.
- Load built assets with `{% vite_asset %}`. Do not reference generated `web/static/dist` files directly.
- Preserve the base layout's early theme script, navigation protocol meta tags, and `hx-boost`/`hx-ext` wiring unless the task explicitly changes their behavior.
- Do not add a parallel navigation mechanism (custom click/popstate routing). Extend `core/navigation/` instead; swaps must only happen when the page protocol (`app-build-id`/`app-navigation-version`) and dynamic-head markers validate, otherwise fall back to a full navigation.

## Navigation and lifecycle

- `core/navigation/setup.ts` picks the adapter from `page-navigation-mode` (`auto`/`native`/`htmx`); HTMX is imported dynamically only in HTMX modes.
- All navigation reports through `app:*` events (`navigation-start` → `before-swap` → `after-swap` → `navigation-end`). Behaviors, transitions, and Solid mount/cleanup hook into these events, not into HTMX-internal events.
- `core/navigation/policy/route-policy.ts` centrally decides which URLs and sources are eligible for local swaps (reserved prefixes, feed, Markdown, and non-HTML routes excluded); do not duplicate denylist rules elsewhere. The native adapter resolves eligible same-origin redirects before commit when the browser supports precommit redirects, and otherwise falls back to a full navigation.

## Behaviors

- A behavior's `mount()` may run on the initial document and repeatedly after `app:after-swap`; it must be safe to run more than once.
- Add shared DOM enhancements through `web/typescript/core/behaviors/` and register them in `core/behaviors/index.ts`.
- Use the behavior runtime's abort signal for listeners and do not mutate a subtree owned by a Solid island.

## Solid islands

- Register every client island in `web/typescript/islands/index.ts`.
- A template island rendered with `{% solid_island %}` also needs a compatible entry in `web/typescript/islands/ssr_registry.ts`; otherwise it fails in production.
- Markdown directive islands are client-rendered. Define allowed directives and props in `native/markdown/src/solid_island.rs` and preserve the sanitizer boundary. Music uses a build-time placeholder loaded by `api/markdown/islands.py`; the client replaces it rather than hydrating it.

## Verification

Choose checks for the affected behavior and layer:

| Pattern | Runtime and scope |
| --- | --- |
| `web/typescript/**/*.test.ts(x)` | Vitest/jsdom for logic and DOM behavior |
| `web/typescript/**/*.browser.test.ts(x)` | Vitest Browser for real browser APIs |
| `web/tests/test_*.py` | Django rendering and server contracts |
| `web/e2e/base/*.spec.ts` | Adapter-independent journeys |
| `web/e2e/htmx/*.spec.ts` | HTMX adapter behavior |
| `web/e2e/native/*.spec.ts` | Native adapter behavior |
| `web/e2e/ssr/*.ssr.spec.ts` | Built SSR output and hydration |

- TypeScript logic and DOM behavior: focused tests through `pnpm test:unit`; use `pnpm test:browser` for real browser APIs and `pnpm typecheck` for TypeScript changes.
- Django views, templates, and Markdown integration: focused test labels under `web.tests` or `api.tests.test_markdown_post_process`, using `uv run manage.py test <test_label>`.
- Native Markdown directives or sanitization: relevant Rust tests in `native/markdown`, plus Python integration coverage when rendered output changes.
- Navigation: the affected adapter suite (`pnpm test:e2e:htmx` or `pnpm test:e2e:native`). For shared navigation changes, exercise both adapters; `pnpm test:e2e:base:htmx` and `pnpm test:e2e:base:native` run shared journeys against each adapter. `pnpm test:e2e` runs the base journeys with the configured mode.
- Template island output or hydration: `pnpm test:ssr`, which already builds SSR assets and runs Django island tests and browser hydration coverage.
- Build configuration, manifests, or static asset integration: `pnpm build:all`, which builds client and SSR assets and runs `collectstatic`. Use `pnpm build` or `pnpm build:ssr` when only that output needs verification.

Reuse current build outputs where the selected check permits it. Avoid rerunning a build already covered by a successful check unless inputs changed or another check requires it. Expand coverage when a change crosses layers or a failure exposes a wider impact.
