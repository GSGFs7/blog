import { queryAllIncludingRoot } from "../dom";
import type { Behavior, BehaviorContext } from "../types";

interface ActiveZoom {
  image: HTMLImageElement;
  clone: HTMLImageElement;
  initialRect: {
    left: number;
    top: number;
    width: number;
    height: number;
  };
}

interface ClosingZoom {
  image: HTMLImageElement;
  clone: HTMLImageElement;
  timer: number;
}

export function createZoomBehavior(): Behavior {
  // mounted images
  const mounted = new Set<HTMLImageElement>();
  // behavior context
  let context: BehaviorContext | undefined;
  // bg overlay DOM
  let overlay: HTMLDivElement | undefined;
  // current zoomed image and its body-mounted clone
  let activeZoom: ActiveZoom | undefined;
  // clone currently playing exit transition
  let closingZoom: ClosingZoom | undefined;

  const removeWindowListeners = () => {
    const window = context?.document.defaultView;
    window?.removeEventListener("scroll", handleScroll);
    window?.removeEventListener("resize", handleResize);
    window?.removeEventListener("keydown", handleKeydown);
    window?.removeEventListener("click", handleOutsideClick);
  };

  const finishClosing = () => {
    if (!closingZoom) {
      return;
    }

    const pending = closingZoom;
    closingZoom = undefined;
    context?.document.defaultView?.clearTimeout(pending.timer);
    pending.clone.remove();
    pending.image.classList.remove("is-zoomed");
  };

  const getContainerOrigin = (doc: Document, win: Window) => {
    const { body } = doc;
    const position = win.getComputedStyle(body).position;
    if (!position || position === "static") {
      return { left: -win.scrollX, top: -win.scrollY };
    }

    const bodyRect = body.getBoundingClientRect();
    return {
      left: bodyRect.left + body.clientLeft,
      top: bodyRect.top + body.clientTop,
    };
  };

  const closeZoom = (immediately = false) => {
    if (!activeZoom) {
      return;
    }

    const { image, clone, initialRect } = activeZoom;
    activeZoom = undefined;
    overlay?.classList.remove("is-visible");
    removeWindowListeners();

    const window = context?.document.defaultView;
    const targetRect =
      !immediately && context?.document.contains(image) ? image.getBoundingClientRect() : undefined;
    const canAnimateBack =
      Boolean(window) && targetRect !== undefined && targetRect.width > 0 && targetRect.height > 0;

    if (immediately || !canAnimateBack || !window || !targetRect || !context) {
      clone.remove();
      image.classList.remove("is-zoomed");
      return;
    }

    clone.style.pointerEvents = "none";
    const origin = getContainerOrigin(context.document, window);
    const targetLeft = targetRect.left - origin.left;
    const targetTop = targetRect.top - origin.top;
    const deltaX = targetLeft + targetRect.width / 2 - (initialRect.left + initialRect.width / 2);
    const deltaY = targetTop + targetRect.height / 2 - (initialRect.top + initialRect.height / 2);
    if (
      deltaX === 0 &&
      deltaY === 0 &&
      targetRect.width === initialRect.width &&
      targetRect.height === initialRect.height
    ) {
      clone.style.transform = "";
    } else {
      const scaleX = targetRect.width / initialRect.width;
      const scaleY = targetRect.height / initialRect.height;
      clone.style.transform =
        scaleX === 1 && scaleY === 1
          ? `translate(${deltaX}px, ${deltaY}px)`
          : `translate(${deltaX}px, ${deltaY}px) scale(${scaleX}, ${scaleY})`;
    }

    finishClosing();
    const timer = window.setTimeout(() => {
      finishClosing();
    }, 300);
    closingZoom = { image, clone, timer };
  };

  const handleKeydown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      closeZoom();
    }
  };

  const handleScroll = () => closeZoom();

  const handleResize = () => closeZoom();

  const handleOutsideClick = (event: MouseEvent) => {
    if (activeZoom && event.target !== activeZoom.clone) {
      closeZoom();
    }
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

  const zoomImage = (image: HTMLImageElement) => {
    if (!context) {
      return;
    }

    if (activeZoom) {
      closeZoom(true);
    }
    finishClosing();

    const rect = image.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
      return;
    }

    // current window object
    const window = context.document.defaultView;
    if (!window) {
      return;
    }

    ensureOverlay();

    // calculate scaling & position
    const padding = window.innerWidth <= 767 ? 16 : 64;
    const viewportScaleX = (window.innerWidth - padding * 2) / rect.width;
    const viewportScaleY = (window.innerHeight - padding * 2) / rect.height;
    const naturalScaleX = image.naturalWidth / rect.width;
    const naturalScaleY = image.naturalHeight / rect.height;
    const scale = Math.min(viewportScaleX, viewportScaleY, naturalScaleX, naturalScaleY);
    const translateX = window.innerWidth / 2 - (rect.left + rect.width / 2);
    const translateY = window.innerHeight / 2 - (rect.top + rect.height / 2);

    const origin = getContainerOrigin(context.document, window);
    const initialLeft = rect.left - origin.left;
    const initialTop = rect.top - origin.top;

    const clone = context.document.createElement("img");
    const src = image.currentSrc || image.src;
    if (src) {
      clone.src = src;
    }
    clone.alt = image.alt;
    clone.className = "zoom-image";
    clone.style.top = `${initialTop}px`;
    clone.style.left = `${initialLeft}px`;
    clone.style.width = `${rect.width}px`;
    clone.style.height = `${rect.height}px`;
    clone.addEventListener(
      "click",
      (event) => {
        event.stopPropagation();
        closeZoom();
      },
      { signal: context.signal },
    );

    image.classList.add("is-zoomed");
    context.document.body.appendChild(clone);
    void clone.offsetWidth;

    activeZoom = {
      image,
      clone,
      initialRect: {
        left: initialLeft,
        top: initialTop,
        width: rect.width,
        height: rect.height,
      },
    };
    clone.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
    overlay?.classList.add("is-visible");

    // these listeners have 2 way to remove
    // 1. user action:
    //    -> handleKeydown/handleScroll/handleResize/handleOutsideClick...
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
    window.addEventListener("resize", handleResize, { once: true });
    window.addEventListener("keydown", handleKeydown);
    window.addEventListener("click", handleOutsideClick);
  };

  return {
    mount(root, behaviorContext) {
      context = behaviorContext;
      const images = queryAllIncludingRoot<HTMLImageElement>(root, ".markdown-body img");
      if (activeZoom && !behaviorContext.document.contains(activeZoom.image)) {
        closeZoom(true);
      }
      if (closingZoom && !behaviorContext.document.contains(closingZoom.image)) {
        finishClosing();
      }
      if (images.length === 0) {
        return;
      }

      ensureOverlay();

      for (const image of images) {
        if (mounted.has(image) || image.closest("[data-solid-island]")) {
          continue;
        }

        mounted.add(image);
        image.classList.add("is-zoomable");
        image.addEventListener(
          "click",
          (event) => {
            event.stopPropagation();
            if (activeZoom?.image === image) {
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
      finishClosing();
      for (const image of mounted) {
        image.classList.remove("is-zoomable");
      }
      mounted.clear();
      overlay?.remove();
      overlay = undefined;
      context = undefined;
    },
  };
}
