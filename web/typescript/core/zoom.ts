let zoomedImg: HTMLImageElement | null = null;
let overlay: HTMLDivElement | null = null;

export function initZoom(root: ParentNode = document) {
  if (typeof document === "undefined") {
    return;
  }

  // append overlay in markdown page only
  const container = root.querySelector(".markdown-body");
  if (!container) {
    return;
  }

  // singleton overlay
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "zoom-overlay";
    overlay.addEventListener("click", closeZoom);
  }

  // add too body
  if (!document.body.contains(overlay)) {
    document.body.appendChild(overlay);
  }

  // avoid error
  if (zoomedImg && !document.contains(zoomedImg)) {
    closeZoom();
  }

  // query all markdown images
  const images = root.querySelectorAll(".markdown-body img");
  images.forEach((img) => {
    img.addEventListener("click", (e) => {
      e.stopPropagation();

      const target = e.target as HTMLImageElement;
      // trigger zoom state
      if (target.classList.contains("is-zoomed")) {
        closeZoom();
      } else {
        zoomImage(target);
      }
    });
  });
}

function zoomImage(img: HTMLImageElement) {
  // must have an image
  if (zoomedImg) {
    closeZoom();
  }

  const rect = img.getBoundingClientRect();
  const padding = 64;

  // 1. Calculate scale based on viewport
  const viewportScaleX = (window.innerWidth - padding * 2) / rect.width;
  const viewportScaleY = (window.innerHeight - padding * 2) / rect.height;

  // 2. Calculate scale based on natural image size (prevent blurriness)
  const naturalScaleX = img.naturalWidth / rect.width;
  const naturalScaleY = img.naturalHeight / rect.height;

  // 3. Take the minimum: don't exceed viewport AND don't exceed natural size
  const scale = Math.min(viewportScaleX, viewportScaleY, naturalScaleX, naturalScaleY);

  zoomedImg = img;
  // viewport center - image center = distance needed to move
  const translateX = window.innerWidth / 2 - (rect.left + rect.width / 2);
  const translateY = window.innerHeight / 2 - (rect.top + rect.height / 2);

  img.classList.add("is-zoomed");
  img.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
  overlay?.classList.add("is-visible");

  window.addEventListener("scroll", closeZoom, { once: true });
  window.addEventListener("keydown", handleKeydown);
  window.addEventListener("click", handleOutsideClick);
}

function closeZoom() {
  if (!zoomedImg) {
    return;
  }

  const img = zoomedImg;
  img.style.transform = "";
  overlay?.classList.remove("is-visible");

  // Wait for the transition to finish before removing the state class
  // This prevents the stacking context from flickering mid-transition
  setTimeout(() => {
    img.classList.remove("is-zoomed");
  }, 300);

  zoomedImg = null;
  window.removeEventListener("keydown", handleKeydown);
  window.removeEventListener("click", handleOutsideClick);
}

function handleOutsideClick(e: MouseEvent) {
  if (zoomedImg && e.target !== zoomedImg) {
    closeZoom();
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    closeZoom();
  }
}
