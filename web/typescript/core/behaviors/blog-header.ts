import { queryAllIncludingRoot } from "./dom";
import type { Behavior } from "./types";

const cardSelector = "[data-blog-header]";

export function createBlogHeaderBehavior(): Behavior {
  const mounted = new WeakSet<HTMLElement>();

  return {
    mount(root, { signal }) {
      for (const card of queryAllIncludingRoot<HTMLElement>(root, cardSelector)) {
        if (mounted.has(card)) {
          continue;
        }

        mounted.add(card);
        card.addEventListener(
          "mousemove",
          (event) => {
            const rect = card.getBoundingClientRect();
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            if (centerX === 0 || centerY === 0) {
              return;
            }

            const x = (event.clientX - (rect.left + centerX)) / centerX;
            const y = (event.clientY - (rect.top + centerY)) / centerY;

            const image = card.querySelector<HTMLImageElement>("[data-blog-header-image]");
            if (image) {
              image.style.transform = `scale(1.1) translateX(${x * 25}px)`;
            }

            const xDisplay = card.querySelector<HTMLElement>("[data-blog-pointer-x]");
            const yDisplay = card.querySelector<HTMLElement>("[data-blog-pointer-y]");
            if (xDisplay) {
              xDisplay.textContent = x.toFixed(2);
            }
            if (yDisplay) {
              yDisplay.textContent = y.toFixed(2);
            }
          },
          { signal },
        );
      }
    },
  };
}
