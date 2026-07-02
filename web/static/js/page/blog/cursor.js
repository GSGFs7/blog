// keep idempotency
(() => {
  const initBlogHeaderCard = (root = document) => {
    const card =
      root instanceof Element
        ? root.querySelector("#blog-header-card")
        : document.getElementById("blog-header-card");

    if (!card || card.dataset.mouseTrackingBound === "true") {
      return;
    }

    card.dataset.mouseTrackingBound = "true";
    card.addEventListener("mousemove", handleMouseMove);
  };

  function handleMouseMove(e) {
    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();

    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const x = (e.clientX - (rect.left + centerX)) / centerX;
    const y = (e.clientY - (rect.top + centerY)) / centerY;

    const img = card.querySelector("img");
    if (img) {
      img.style.transform = `scale(1.1) translateX(${x * 25}px)`;
    }

    const xDisplay = document.getElementById("blog-mouse-position-x");
    const yDisplay = document.getElementById("blog-mouse-position-y");
    if (xDisplay) {
      xDisplay.textContent = x.toFixed(2);
    }
    if (yDisplay) {
      yDisplay.textContent = y.toFixed(2);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => initBlogHeaderCard(), {once: true});
  } else {
    initBlogHeaderCard();
  }

  // potential resource leaks?
  document.body.addEventListener("htmx:load", (event) => {
    initBlogHeaderCard(event.target);
  });
})();
