import { queryAllIncludingRoot } from "./dom";
import type { Behavior, BehaviorContext } from "./types";

export function createZoomBehavior(): Behavior {
  // mounted images
  const mounted = new WeakSet<HTMLImageElement>();
  // exit animation timers
  const classRemovalTimers = new Map<HTMLImageElement, number>();
  // behavior context
  let context: BehaviorContext | undefined;
  // bg overlay DOM
  let overlay: HTMLDivElement | undefined;
  // current zoomed image
  let zoomedImage: HTMLImageElement | undefined;

  const removeWindowListeners = () => {
    const window = context?.document.defaultView;
    window?.removeEventListener("scroll", handleScroll);
    window?.removeEventListener("keydown", handleKeydown);
    window?.removeEventListener("click", handleOutsideClick);
  };

  const clearPendingClassRemoval = (image: HTMLImageElement) => {
    const timer = classRemovalTimers.get(image);
    if (timer === undefined) {
      return;
    }

    context?.document.defaultView?.clearTimeout(timer);
    classRemovalTimers.delete(image);
  };

  const closeZoom = (immediately = false) => {
    if (!zoomedImage) {
      return;
    }

    const image = zoomedImage;
    image.style.transform = "";
    overlay?.classList.remove("is-visible");
    zoomedImage = undefined;
    removeWindowListeners();

    clearPendingClassRemoval(image);
    if (immediately) {
      image.classList.remove("is-zoomed");
      return;
    }

    const window = context?.document.defaultView;
    if (!window) {
      image.classList.remove("is-zoomed");
      return;
    }

    const timer = window.setTimeout(() => {
      image.classList.remove("is-zoomed");
      classRemovalTimers.delete(image);
    }, 300);
    classRemovalTimers.set(image, timer);
  };

  const handleKeydown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      closeZoom();
    }
  };

  const handleScroll = () => closeZoom();

  const handleOutsideClick = (event: MouseEvent) => {
    if (zoomedImage && event.target !== zoomedImage) {
      closeZoom();
    }
  };

  const zoomImage = (image: HTMLImageElement) => {
    if (!context) {
      return;
    }

    if (zoomedImage) {
      closeZoom(true);
    }
    clearPendingClassRemoval(image);

    const rect = image.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
      return;
    }

    // current window object
    const window = context.document.defaultView;
    if (!window) {
      return;
    }

    // calculate scaling & position
    const padding = 64;
    const viewportScaleX = (window.innerWidth - padding * 2) / rect.width;
    const viewportScaleY = (window.innerHeight - padding * 2) / rect.height;
    const naturalScaleX = image.naturalWidth / rect.width;
    const naturalScaleY = image.naturalHeight / rect.height;
    const scale = Math.min(viewportScaleX, viewportScaleY, naturalScaleX, naturalScaleY);
    const translateX = window.innerWidth / 2 - (rect.left + rect.width / 2);
    const translateY = window.innerHeight / 2 - (rect.top + rect.height / 2);

    zoomedImage = image;
    image.classList.add("is-zoomed");
    image.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
    overlay?.classList.add("is-visible");

    // these listeners have 2 way to remove
    // 1. user action:
    //    -> handleKeydown/handleScroll/handleOutsideClick...
    //    -> closeZoom()
    //    -> removeWindowListeners()
    // 2. runtime destroy
    //    -> controller.abort()
    //    -> behavior.destroy()
    //    -> closeZoom(true)
    //    -> removeWindowListeners()
    //
    // remember remove the listener in `removeWindowListeners()` if add a new listener here
    window.addEventListener("scroll", handleScroll, { once: true });
    window.addEventListener("keydown", handleKeydown);
    window.addEventListener("click", handleOutsideClick);
  };

  const ensureOverlay = () => {
    if (!context || (overlay && context.document.contains(overlay))) {
      return;
    }

    overlay = context.document.createElement("div");
    overlay.id = "zoom-overlay";
    overlay.addEventListener("click", () => closeZoom(), { signal: context.signal });
    context.document.body.appendChild(overlay);
  };

  return {
    mount(root, behaviorContext) {
      context = behaviorContext;
      const images = queryAllIncludingRoot<HTMLImageElement>(root, ".markdown-body img");
      if (images.length === 0) {
        if (zoomedImage && !behaviorContext.document.contains(zoomedImage)) {
          closeZoom(true);
        }
        return;
      }

      ensureOverlay();
      if (zoomedImage && !behaviorContext.document.contains(zoomedImage)) {
        closeZoom(true);
      }

      for (const image of images) {
        if (mounted.has(image)) {
          continue;
        }

        mounted.add(image);
        image.addEventListener(
          "click",
          (event) => {
            event.stopPropagation();
            if (image === zoomedImage) {
              closeZoom();
            } else {
              zoomImage(image);
            }
          },
          { signal: behaviorContext.signal },
        );
      }
    },
    destroy() {
      closeZoom(true);
      for (const [image, timer] of classRemovalTimers) {
        context?.document.defaultView?.clearTimeout(timer);
        image.classList.remove("is-zoomed");
      }
      classRemovalTimers.clear();
      overlay?.remove();
      overlay = undefined;
      context = undefined;
    },
  };
}
