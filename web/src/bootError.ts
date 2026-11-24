/** Plain-DOM recovery when asynchronous startup fails before React can mount. */
export function renderBootError(root: HTMLElement, reload: () => void = () => window.location.reload()): void {
  const main = document.createElement("main");
  main.className = "mx-auto max-w-2xl p-6";
  const box = document.createElement("section");
  box.setAttribute("role", "alert");
  box.className = "grid gap-4 rounded-lg border border-border bg-card p-6 text-card-foreground";
  const heading = document.createElement("h1");
  heading.textContent = "Something went wrong";
  heading.tabIndex = -1;
  heading.className = "text-2xl font-semibold";
  const p = document.createElement("p");
  p.textContent = "We couldn't load this page. Reload to try again, or go back to the start.";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "Reload page";
  btn.className = "min-h-11 rounded-md border border-border px-4 py-2 font-medium";
  btn.addEventListener("click", reload);
  const back = document.createElement("a");
  back.href = "/";
  back.textContent = "Back to the start";
  back.className = "text-primary underline underline-offset-4";
  box.append(heading, p, btn, back);
  main.append(box);
  root.replaceChildren(main);
  heading.focus();
}
