# Frontend Agent Guide

Frontend architecture maybe is a bit complex. Read `../docs/agent-guide/frontend-architecture.md` before making a frontend change. It explains the rendering lifecycle, ownership boundaries, and build steps.

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
- Markdown directive islands are client-rendered. Add only intentional, sanitized directives to `api/markdown/post_processors.py`; add SSR support only when the component is browser-independent.

## Verification

Run the checks that match the change: `pnpm test`, `pnpm test:e2e` (adapter-independent journeys), `pnpm test:e2e:htmx`, `pnpm test:e2e:native`, `pnpm test:ssr`, `pnpm typecheck`, `pnpm build:all`, and focused Django tests under `web/tests/`. Use `pnpm test:e2e:base:htmx` and `pnpm test:e2e:base:native` to verify the shared journeys against a forced adapter.
