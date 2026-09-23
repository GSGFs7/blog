---
name: frontend-architecture
description: "Describe the project's frontend architecture: server-first Django rendering, the protocol-driven navigation layer, Solid islands, Markdown integration, and Vite assets. Use to understand layer ownership and cross-layer integration."
---

# Frontend Architecture

The frontend is server-first and progressively enhanced. Django renders pages, a protocol-driven navigation layer selects an HTMX or Native Navigation API adapter per deployment mode, Solid powers on-demand interactive islands, and Vite builds client and SSR assets.

## Layer ownership

| Concern | Layer |
| --- | --- |
| Page content, reading flow, or basic navigation | Django view and template |
| Server-backed replacement, pagination, or form response | Django fragment with the existing navigation or HTMX interaction |
| Small enhancement to existing HTML | `web/typescript/core/behaviors/` |
| Complex, isolated local state | `web/typescript/islands/` |
| Interactive Markdown directive | `native/markdown/src/solid_island.rs` plus a client island; `api/markdown/islands.py` loads the music placeholder |
| Django admin interaction | `web/typescript/admin/` |

Entire pages, article bodies, and basic navigation are not Solid islands.

## Details

[references/architecture.md](references/architecture.md) covers the system model, the ownership map, the rendering and navigation lifecycle, behaviors, Solid islands and SSR, and styles, assets, and builds. Frontend invariants are listed in [web/AGENTS.md](../../../web/AGENTS.md).
