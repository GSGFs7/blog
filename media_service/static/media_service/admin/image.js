(() => {
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-copy-image-url]");
    if (!button || button.disabled) {
      return;
    }

    const url = button.dataset.copyImageUrl;
    button.disabled = true;

    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }

      await navigator.clipboard.writeText(url);
    } finally {
      button.disabled = false;
      button.focus();
    }
  });
})();
