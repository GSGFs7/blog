import { createArticleLinkBehavior } from "./implementations/article-links";
import { createBlogHeaderBehavior } from "./implementations/blog-header";
import { createCodeExpanderBehavior } from "./implementations/code-expander";
import { createImagePlaceholderBehavior } from "./implementations/image-placeholder";
import { createItalicEmojiBehavior } from "./implementations/italic-emoji";
import { createMobileDecorationBehavior } from "./implementations/mobile-decoration";
import { createZoomBehavior } from "./implementations/zoom";
import type { BehaviorDefinition } from "./types";

export const behaviorRegistry = [
  {
    selector: "[data-blog-header]",
    inline: createBlogHeaderBehavior,
  },
  {
    selector: ".markdown-body pre, .markdown-body .terminal",
    inline: createCodeExpanderBehavior,
  },
  {
    selector: "[data-mobile-undecorated]",
    inline: createMobileDecorationBehavior,
  },
  {
    selector: "img.image-placeholder",
    inline: createImagePlaceholderBehavior,
  },
  {
    selector: ".markdown-body img",
    inline: createZoomBehavior,
  },
  {
    selector: ".markdown-body a[href]",
    inline: createArticleLinkBehavior,
  },
  {
    selector: ".markdown-body em, .markdown-body i",
    inline: createItalicEmojiBehavior,
  },
] satisfies readonly BehaviorDefinition[];
