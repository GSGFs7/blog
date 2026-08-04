import type { LazyBehavior } from "./types";

export const behaviorRegistry = [
  {
    selector: "[data-blog-header]",
    load: async () => (await import("./implementations/blog-header")).createBlogHeaderBehavior,
  },
  {
    selector: ".markdown-body pre, .markdown-body .terminal",
    load: async () => (await import("./implementations/code-expander")).createCodeExpanderBehavior,
  },
  {
    selector: "[data-mobile-undecorated]",
    load: async () => (await import("./implementations/mobile-decoration")).createMobileDecorationBehavior,
  },
  {
    selector: ".markdown-body img",
    load: async () => (await import("./implementations/zoom")).createZoomBehavior,
  },
] satisfies readonly LazyBehavior[];
