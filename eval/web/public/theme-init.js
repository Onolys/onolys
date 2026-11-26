// Runs before first paint (classic script, allowed by CSP script-src 'self'): applies the saved theme override.
// Keep the key and values in sync with web/src/lib/theme.ts and web/public/theme-init.js (the prod copy).
(function () {
  try {
    var t = localStorage.getItem("onolys-theme");
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  } catch {
    /* storage blocked: follow the OS */
  }
})();
