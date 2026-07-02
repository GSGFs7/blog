(() => {
  const root = document.documentElement;
  if (root.dataset.imageDescriptionToggleBound === "true") {
    return;
  }

  root.dataset.imageDescriptionToggleBound = "true";
  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }

    const button = event.target.closest("[data-image-description-toggle]");
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }

    const descriptionId = button.getAttribute("aria-controls");
    const description = descriptionId && document.getElementById(descriptionId);
    if (!description) {
      return;
    }

    const isHidden = description.classList.toggle("hidden");
    button.setAttribute("aria-expanded", String(!isHidden));
  });
})();
