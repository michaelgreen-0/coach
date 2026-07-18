import { S } from "../core/state.js";
import { $, el } from "../core/dom.js";
import { show, notice } from "../core/view.js";
import { api } from "../core/api.js";
import { tocRow } from "../core/components.js";
import { startQuiz } from "./quiz.js";
import { showDashboard } from "./dashboard.js";
import { openTutor } from "./tutor.js";
import { goHome } from "./subjects.js";

// needsAuth items lean on saved progress, so they only show for signed-in users.
export const MENU_STUDY = [
  { key: "1", label: "quiz — all questions", sub: "weakest first", run: () => startQuiz("all") },
  { key: "2", label: "quiz — pick a topic", run: showTopics },
  { key: "3", label: "quiz — my weak areas", needsAuth: true, run: () => startQuiz("weak") },
  { key: "4", label: "quiz — unseen questions", needsAuth: true, run: () => startQuiz("unseen") },
  { key: "5", label: "review — questions i got wrong", needsAuth: true, run: () => startQuiz("missed") },
];

async function loadState() {
  const params = new URLSearchParams();
  if (S.subject) params.set("subject", S.subject);
  if (S.set) params.set("set", S.set);
  const qs = params.toString();
  S.info = await api("/api/state" + (qs ? `?${qs}` : ""));
  renderSetSwitch();
  renderMenu();
}

function renderSetSwitch() {
  const wrap = $("set-switch");
  const sel = $("set-select");
  if (!S.info.sets.length) { wrap.hidden = true; return; }
  wrap.hidden = false;
  sel.replaceChildren();
  const all = el("option", null, "all sets");
  all.value = "";
  sel.append(all);
  for (const s of S.info.sets) {
    const o = el("option", null, s);
    o.value = s;
    sel.append(o);
  }
  sel.value = S.set || "";
}

function renderMenu() {
  $("subject").textContent = S.info.name;
  const where = S.set ? ` — ${S.set}` : "";
  $("bank-meta").textContent = `${S.info.question_count} questions${where}`;

  const banner = $("session-banner");
  banner.hidden = !S.sessionMsg;
  if (S.sessionMsg) banner.textContent = S.sessionMsg;

  const signedIn = S.info.signed_in;

  const study = $("menu-study");
  study.replaceChildren();
  for (const item of MENU_STUDY) {
    if (item.needsAuth && !signedIn) continue;
    // "weakest first" only applies once there's progress to sort by
    const sub = signedIn ? item.sub : null;
    study.append(tocRow(item.key, item.label, sub, item.key === "1" ? S.info.question_count : null, item.run));
  }

  const prog = $("menu-progress");
  prog.replaceChildren();
  if (signedIn) {
    prog.append(tocRow("6", "progress dashboard", null, null, showDashboard));
  }
  if (S.info.tutor_on && signedIn) {
    prog.append(tocRow("7", "talk to the tutor", null, null, () => openTutor(null, "menu")));
  }
  if (S.subjects.length > 1) {
    prog.append(tocRow("c", "switch subject", null, null, goHome));
  }
  $("progress-head").hidden = !prog.children.length;

  const signinHint = $("signin-hint");
  signinHint.hidden = signedIn;
  if (!signedIn) {
    signinHint.textContent = "sign in to track progress, target your weak areas, and use the tutor.";
  }

  const hint = $("tutor-hint");
  hint.hidden = !S.info.tutor_disabled_hint;
  if (S.info.tutor_disabled_hint) hint.textContent = S.info.tutor_disabled_hint;

  show("menu");
}

export function backToMenu() {
  loadState().catch((e) => notice(e.message));
}

export function showTopics() {
  const list = $("topic-list");
  list.replaceChildren();
  S.info.topics.forEach((t, i) => {
    list.append(tocRow(String(i + 1), t.name, null, `${t.questions} questions`,
      () => startQuiz("topic", t.name)));
  });
  show("topics");
}

$("set-select").addEventListener("change", (e) => {
  S.set = e.target.value || null;
  S.sessionMsg = null;
  backToMenu();
});
