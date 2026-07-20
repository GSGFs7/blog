# Frontend Agent Guide

Frontend architecture maybe is a bit complex. Read `../docs/agent-guide/frontend-architecture.md` before making a frontend change. It explains the rendering lifecycle, ownership boundaries, and build steps.

## No-JS baseline

- Keep main page content fully readable and basic navigation functional without JavaScript.
- Treat JavaScript as progressive enhancement. Interactive features such as comments and rich widgets do not need a no-JS implementation unless the task requires one.

## Non-negotiable rules

- Use Django templates for pages and content, HTMX for progressive navigation or partial replacement, behaviors for small DOM enhancements, and Solid islands for isolated stateful interaction.
- Load built assets with `{% vite_asset %}`. Do not reference generated `web/static/dist` files directly.
- Preserve the base layout's early theme script, HTMX setup, and `hx-boost` unless the task explicitly changes their behavior.

## HTMX and behaviors

- A behavior's `mount()` may run on the initial document and repeatedly after `htmx:load`; it must be safe to run more than once.
- Add shared DOM enhancements through `web/typescript/core/behaviors/` and register them in `core/behaviors/index.ts`.
- Use the behavior runtime's abort signal for listeners and do not mutate a subtree owned by a Solid island.

## Solid islands

- Register every client island in `web/typescript/islands/index.ts`.
- A template island rendered with `{% solid_island %}` also needs a compatible entry in `web/typescript/islands/ssr_registry.ts`; otherwise it fails in production.
- Markdown directive islands are client-rendered. Add only intentional, sanitized directives to `api/markdown/post_processors.py`; add SSR support only when the component is browser-independent.

## Verification

Run the checks that match the change: `pnpm test`, `pnpm typecheck`, `pnpm build:all`, and focused Django tests under `web/tests/`.
