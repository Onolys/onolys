/* Independent of the module bundle: recover failed imports/assets before React mounts. */
(function () {
  function recover() {
    var recovery = document.getElementById("startup-recovery");
    if (!recovery) return;
    recovery.setAttribute("role", "alert");
    var heading = recovery.querySelector("h1");
    heading.textContent = "Something went wrong";
    heading.focus();
    recovery.querySelector("p").textContent = "We couldn't load this page. Reload to try again, or go back to the start.";
  }
  window.addEventListener("error", recover, true);
  window.addEventListener("unhandledrejection", recover);
  window.addEventListener("vite:preloadError", recover);
})();
