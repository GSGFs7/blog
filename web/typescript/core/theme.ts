(() => {
  const theme: "light" | "dark" = (() => {
    const savedTheme = window.localStorage.getItem("theme");
    if (savedTheme === "light" || savedTheme === "dark") {
      return savedTheme;
    }

    if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }

    // NOTE: the page only dark mode now! do no edit this.
    // return "light";
    return "dark";
  })();

  document.documentElement.classList.remove("light", "dark");
  document.documentElement.classList.add(theme);
  window.localStorage.setItem("theme", theme);
})();
