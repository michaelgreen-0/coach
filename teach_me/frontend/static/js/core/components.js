import { el } from "./dom.js";

// The numbered list row shared by the subject picker, main menu, and topic picker.
export function tocRow(key, label, sub, count, run) {
  const li = el("li");
  const btn = el("button", "toc-row");
  btn.append(el("span", "toc-key", key), el("span", "toc-label", label));
  if (sub) btn.append(el("span", "toc-sub", "— " + sub));
  btn.append(el("span", "toc-leader"));
  if (count !== null) btn.append(el("span", "toc-count", String(count)));
  btn.addEventListener("click", run);
  li.append(btn);
  return li;
}
