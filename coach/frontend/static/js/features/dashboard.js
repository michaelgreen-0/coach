import { S } from "../core/state.js";
import { $, el } from "../core/dom.js";
import { show, notice } from "../core/view.js";
import { api } from "../core/api.js";

export async function showDashboard() {
  const params = new URLSearchParams();
  if (S.subject) params.set("subject", S.subject);
  if (S.set) params.set("set", S.set);
  const qs = params.toString();
  let d;
  try {
    d = await api("/api/dashboard" + (qs ? `?${qs}` : ""));
  } catch (e) { notice(e.message); return; }

  const body = $("dash-table").tBodies[0];
  body.replaceChildren();
  for (const t of d.topics) {
    const tr = el("tr");
    tr.append(el("td", null, t.topic));
    tr.append(el("td", "num", `${t.seen}/${t.questions}`));
    tr.append(el("td", "num", String(t.attempts)));
    const acc = el("td", "num", t.accuracy === null ? "—" : `${Math.round(100 * t.accuracy)}%`);
    tr.append(acc);
    const barCell = el("td");
    const bar = el("div", "acc-bar");
    if (t.accuracy !== null) {
      const fill = el("div", "acc-fill " +
        (t.accuracy >= 0.8 ? "good" : t.accuracy >= 0.6 ? "mid" : "bad"));
      // keep a visible sliver at 0% so it doesn't read as "never attempted"
      fill.style.width = `${Math.max(2, Math.round(100 * t.accuracy))}%`;
      bar.append(fill);
    }
    barCell.append(bar);
    tr.append(barCell);
    body.append(tr);
  }

  const c = d.coverage;
  $("dash-coverage").replaceChildren(
    "bank coverage: ",
    el("strong", null, `${c.seen}/${c.total}`),
    " attempted, ",
    el("strong", null, String(c.mastered)),
    " mastered (answered correctly twice in a row)",
  );

  const focus = $("dash-focus");
  focus.hidden = !d.focus.length;
  if (d.focus.length) {
    focus.replaceChildren("focus areas: ");
    d.focus.forEach((f, i) => {
      if (i) focus.append(", ");
      focus.append(el("span", "focus-mark", `${f.topic} (${Math.round(100 * f.accuracy)}%)`));
    });
  }

  const overall = $("dash-overall");
  overall.hidden = d.overall === null;
  if (d.overall !== null) {
    const verdict = d.overall >= 0.8 ? "looking strong — aim to keep it above 80%"
      : d.overall >= 0.65 ? "getting there — target 80%+"
      : "keep drilling — target 80%+";
    overall.replaceChildren(
      "overall accuracy: ",
      el("strong", null, `${Math.round(100 * d.overall)}%`),
      ` — ${verdict}`,
    );
  }

  show("dashboard");
}
