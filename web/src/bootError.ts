/** Plain-DOM fallback for a failed boot (no React, so it works when the app can't start). */
export function renderBootError(root: HTMLElement, reload: () => void = () => window.location.reload()): void {
  const box = document.createElement("div");
  box.setAttribute("role", "alert");
  const p = document.createElement("p");
  p.textContent = "Can't start the app. Reload the page.";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "Reload";
  btn.addEventListener("click", reload);
  box.append(p, btn);
  root.replaceChildren(box);
}
