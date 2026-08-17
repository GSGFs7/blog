import { queryAllIncludingRoot } from "../dom";
import type { Behavior } from "../types";

const selector = "img.image-placeholder";

export function createImagePlaceholderBehavior(): Behavior {
  const mounted = new WeakSet<HTMLImageElement>();

  return {
    mount(root, { signal }) {
      for (const image of queryAllIncludingRoot<HTMLImageElement>(root, selector)) {
        if (image.closest("[data-solid-island]")) {
          continue;
        }
        if (image.complete && image.naturalWidth > 0) {
          image.classList.remove("image-placeholder");
          continue;
        }
        if (mounted.has(image)) {
          continue;
        }

        mounted.add(image);
        image.addEventListener("load", () => image.classList.remove("image-placeholder"), {
          once: true,
          signal,
        });
      }
    },
  };
}
