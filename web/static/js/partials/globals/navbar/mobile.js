(() => {
  const closeGuardMs = 250;
  const menu = document.getElementById("mobile-menu");

  const openMobileMenu = (event) => {
    event?.stopPropagation();
    if (!menu) return;
    menu.dataset.openedAt = String(Date.now());
    menu.classList.add("is-open");
  };

  const closeMobileMenu = (event) => {
    event?.stopPropagation();
    if (!menu) return;
    const openedAt = Number(menu.dataset.openedAt || 0);
    if (Date.now() - openedAt < closeGuardMs) return;
    menu.classList.remove("is-open");
  };

  document.querySelector("[data-mobile-menu-open]")?.addEventListener("click", openMobileMenu);

  document.querySelector("[data-mobile-menu-close]")?.addEventListener("click", closeMobileMenu);

  document.querySelectorAll(".site-mobile-menu__link").forEach(link => {
    link.addEventListener("click", closeMobileMenu);
  });
})();
