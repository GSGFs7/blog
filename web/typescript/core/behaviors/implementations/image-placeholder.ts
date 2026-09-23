import { queryAllIncludingRoot } from "../dom";
import type { Behavior } from "../types";

const selector = "img.image-placeholder";

function clearPlaceholder(image: HTMLImageElement) {
  image.style.removeProperty("background-image");
  image.style.removeProperty("background-size");
  image.classList.remove("image-placeholder");
}

export function createImagePlaceholderBehavior(): Behavior {
  const mounted = new WeakSet<HTMLImageElement>();

  return {
    mount(root, { signal }) {
      for (const image of queryAllIncludingRoot<HTMLImageElement>(root, selector)) {
        if (image.closest("[data-solid-island]")) {
          continue;
        }
        if (image.complete && image.naturalWidth > 0) {
          clearPlaceholder(image);
          continue;
        }
        if (mounted.has(image)) {
          continue;
        }

        mounted.add(image);
        image.addEventListener("load", () => clearPlaceholder(image), {
          once: true,
          signal,
        });
      }
    },
  };
}
