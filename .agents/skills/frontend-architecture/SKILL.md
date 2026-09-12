---
name: frontend-architecture
description: Guide architectural decisions across Django rendering, navigation, Solid islands, Markdown, and Vite. Use for layer ownership or cross-layer integration, not localized edits answerable from the affected code.
---

# Frontend Architecture

Understand and preserve the project's server-first, progressively enhanced frontend architecture.

## Relevant Guidance

Use [web/AGENTS.md](../../../web/AGENTS.md) for frontend invariants, including when integrating Markdown or native code outside `web/`. Consult the relevant section of [references/architecture.md](references/architecture.md) when resolving navigation lifecycle, SSR, Markdown rendering, or asset ownership. The layer table below is sufficient for straightforward ownership decisions.

## Choose the Layer

| Need | Use |
| --- | --- |
| Page content, reading flow, or basic navigation | Django view and template |
| Server-backed replacement, pagination, or form response | Django fragment and the existing navigation or HTMX interaction |
| Small enhancement to existing HTML | `web/typescript/core/behaviors/` |
| Complex, isolated local state | `web/typescript/islands/` |
| Interactive Markdown directive | `native/markdown/src/solid_island.rs` plus a client island; `api/markdown/islands.py` loads the music placeholder |
| Django admin interaction | `web/typescript/admin/` |

Do not turn an entire page, article body, or basic navigation into a Solid island.

## Verify the Change

Use [Test selection](references/architecture.md#test-selection) to choose checks for the affected behavior and build outputs.

Do not assert generated Solid hydration markers or hand-copy generated SSR markup.
