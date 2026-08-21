---
name: frontend-architecture
description: Rules for changing this project's public frontend (Django templates/views, HTMX fragments, TypeScript behaviors/islands, navigation lifecycle, SSR, Markdown directives, Vite config, frontend tests). Load ONLY when the task actually edits frontend source code or runs frontend checks. Do not load for frontend questions, reviews, or debugging that involve no code changes.
---

# Frontend Architecture

Preserve the project's server-first, progressively enhanced frontend while making changes.

## Start Every Task

1. Read [references/architecture.md](references/architecture.md) before changing frontend code if you have not already read it this session; for small, single-layer changes you may rely on the rules below instead.
2. Inspect the affected implementation, nearby tests, and any scoped `AGENTS.md` files.
3. Choose the smallest responsible layer before writing code.
4. Preserve the navigation lifecycle and no-JavaScript baseline.
5. Run the narrowest relevant checks, expanding coverage when the change crosses layers.

## Choose the Layer

| Need | Use |
| --- | --- |
| Page content, reading flow, or basic navigation | Django view and template |
| Server-backed replacement, pagination, or form response | Django fragment and HTMX |
| Small enhancement to existing HTML | `web/typescript/core/behaviors/` |
| Complex, isolated local state | `web/typescript/islands/` |
| Interactive Markdown directive | `api/markdown/post_processors.py` plus a client island |
| Django admin interaction | `web/typescript/admin/` |

Do not turn an entire page, article body, or basic navigation into a Solid island.

## Preserve the Architecture

- Keep main content and basic navigation functional without JavaScript.
- Treat Django templates as the source of page content and SEO semantics.
- Extend `core/navigation/` instead of adding click or history routing in parallel.
- Use the public `app:*` lifecycle for behavior and island cleanup/remounting; do not bind application features to HTMX-internal lifecycle events.
- Require page protocol and dynamic-head validation before a client-side swap; fall back to a full navigation on mismatch.
- Make behaviors idempotent, scope queries to their root, register listeners with the runtime abort signal, and leave Solid-owned subtrees untouched.
- Register every client island in `islands/index.ts`. Also register template-rendered islands in `islands/ssr_registry.ts` with safe placeholder props.
- Treat Markdown directive mappings and the HTML sanitizer allowlist as a security boundary.
- Load source entries through Django Vite template tags. Never edit generated assets or hard-code generated filenames.

## Verify the Change

Select checks from the reference according to the affected layer. At minimum:

- Run focused Vitest tests for TypeScript logic or components.
- Run focused Django tests for views, templates, template tags, and Markdown processing.
- Run adapter-specific Playwright coverage for navigation changes.
- Run SSR tests and `pnpm build:all` for template islands, hydration, manifests, or build changes.
- Run `pnpm typecheck` for TypeScript changes.

Do not assert generated Solid hydration markers or hand-copy generated SSR markup.
