/* teach-me web UI. One state machine, same flows as the CLI. */

"use strict";

const S = {
  username: null,  // signed-in user
  authMode: "login",
  inviteRequired: false,
  chapters: [],    // /api/chapters payload
  chapter: null,   // active chapter slug
  info: null,      // /api/state payload
  set: null,       // active question set, null = all
  quiz: null,      // {pool, i, asked, correct, mode, focus, stage, selected, graded}
  tutor: null,     // {history, qid, stage, correct, picked, returnTo}
  view: "auth",
  sessionMsg: null,
};

const $ = (id) => document.getElementById(id);
const VIEWS = ["auth", "chapters", "menu", "topics", "quiz", "done", "dashboard", "tutor"];

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function letter(i) { return String.fromCharCode(65 + i); }

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // a session can expire mid-use; anything but the sign-in form goes back to it
    if (res.status === 401 && S.view !== "auth") showAuth();
    const err = new Error(data.error || `request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function show(view) {
  S.view = view;
  for (const v of VIEWS) $("view-" + v).hidden = v !== view;
  $("notice").hidden = true;
  setFootKeys(view);
}

function notice(text) {
  const n = $("notice");
  n.textContent = text;
  n.hidden = false;
}

function setFootKeys(view) {
  const f = $("foot-keys");
  const tut = S.info && S.info.tutor_on;
  if (view === "quiz" && S.quiz) {
    const last = letter(S.quiz.pool[S.quiz.i].options.length - 1).toLowerCase();
    f.textContent = S.quiz.stage === "answering"
      ? `a–${last} select · enter check · s skip${tut ? " · t tutor" : ""} · m menu`
      : `enter next${tut ? " · t tutor" : ""} · m menu`;
  } else {
    f.textContent = "";
  }
}

/* ── Sign in ─────────────────────────────────────────────── */

function showAuth() {
  S.username = null;
  renderUserChip();
  $("set-switch").hidden = true;
  setAuthMode(S.authMode);
  show("auth");
  $("auth-username").focus();
}

function setAuthMode(mode) {
  S.authMode = mode;
  const login = mode === "login";
  $("auth-sub").textContent = login
    ? "sign in to pick up where you left off."
    : "make an account — your progress is yours alone.";
  $("auth-submit").textContent = login ? "sign in" : "create account";
  $("auth-toggle").textContent = login
    ? "new here? create an account"
    : "have an account? sign in";
  $("auth-invite-field").hidden = login || !S.inviteRequired;
  $("auth-password").autocomplete = login ? "current-password" : "new-password";
  $("auth-error").hidden = true;
}

function renderUserChip() {
  $("user-chip").hidden = !S.username;
  if (S.username) $("user-name").textContent = S.username + " ·";
}

async function signedIn(username) {
  S.username = username;
  renderUserChip();
  await loadChapters();
}

$("auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = $("auth-username").value.trim();
  const password = $("auth-password").value;
  const errBox = $("auth-error");
  errBox.hidden = true;
  try {
    const data = S.authMode === "login"
      ? await api("/api/login", { username, password })
      : await api("/api/register", { username, password, invite: $("auth-invite").value.trim() });
    $("auth-password").value = "";
    await signedIn(data.username);
  } catch (err) {
    errBox.textContent = err.message;
    errBox.hidden = false;
  }
});

$("auth-toggle").addEventListener("click", () => {
  setAuthMode(S.authMode === "login" ? "register" : "login");
  $("auth-username").focus();
});

$("sign-out").addEventListener("click", async () => {
  try { await api("/api/logout", {}); } catch { /* signing out locally regardless */ }
  S.chapter = null;
  S.chapters = [];
  S.set = null;
  S.quiz = null;
  S.sessionMsg = null;
  S.authMode = "login";
  showAuth();
});

/* ── Chapter picker ──────────────────────────────────────── */

async function loadChapters() {
  const data = await api("/api/chapters");
  S.chapters = data.chapters;
  if (S.chapters.length === 1) {
    selectChapter(S.chapters[0].slug);
  } else {
    renderChapters();
  }
}

function renderChapters() {
  const list = $("chapter-list");
  list.replaceChildren();
  S.chapters.forEach((ch, i) => {
    list.append(tocRow(String(i + 1), ch.subject, null,
      `${ch.question_count} questions`, () => selectChapter(ch.slug)));
  });
  show("chapters");
}

function selectChapter(slug) {
  S.chapter = slug;
  S.set = null;
  S.sessionMsg = null;
  backToMenu();
}

function goHome() {
  if (S.chapters.length > 1) {
    S.sessionMsg = null;
    renderChapters();
  } else if (S.chapter) {
    backToMenu();
  }
}

/* ── Menu ────────────────────────────────────────────────── */

const MENU_STUDY = [
  { key: "1", label: "quiz — all questions", sub: "weakest first", run: () => startQuiz("all") },
  { key: "2", label: "quiz — pick a topic", run: showTopics },
  { key: "3", label: "quiz — my weak areas", run: () => startQuiz("weak") },
  { key: "4", label: "quiz — unseen questions", run: () => startQuiz("unseen") },
  { key: "5", label: "review — questions i got wrong", run: () => startQuiz("missed") },
];

function tocRow(key, label, sub, count, run) {
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

async function loadState() {
  const params = new URLSearchParams();
  if (S.chapter) params.set("chapter", S.chapter);
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
  $("subject").textContent = S.info.subject;
  const where = S.set ? ` — ${S.set}` : "";
  $("bank-meta").textContent = `${S.info.question_count} questions${where}`;

  const banner = $("session-banner");
  banner.hidden = !S.sessionMsg;
  if (S.sessionMsg) banner.textContent = S.sessionMsg;

  const study = $("menu-study");
  study.replaceChildren();
  for (const item of MENU_STUDY) {
    study.append(tocRow(item.key, item.label, item.sub, item.key === "1" ? S.info.question_count : null, item.run));
  }

  const prog = $("menu-progress");
  prog.replaceChildren();
  prog.append(tocRow("6", "progress dashboard", null, null, showDashboard));
  if (S.info.tutor_on) {
    prog.append(tocRow("7", "talk to the tutor", null, null, () => openTutor(null, "menu")));
  }
  if (S.chapters.length > 1) {
    prog.append(tocRow("c", "switch chapter", null, null, goHome));
  }

  const hint = $("tutor-hint");
  hint.hidden = !S.info.tutor_disabled_hint;
  if (S.info.tutor_disabled_hint) hint.textContent = S.info.tutor_disabled_hint;

  show("menu");
}

function backToMenu() {
  loadState().catch((e) => notice(e.message));
}

/* ── Topic picker ────────────────────────────────────────── */

function showTopics() {
  const list = $("topic-list");
  list.replaceChildren();
  S.info.topics.forEach((t, i) => {
    list.append(tocRow(String(i + 1), t.name, null, `${t.questions} questions`,
      () => startQuiz("topic", t.name)));
  });
  show("topics");
}

/* ── Quiz ────────────────────────────────────────────────── */

async function startQuiz(mode, topic = null) {
  let data;
  try {
    data = await api("/api/quiz", { mode, topic, set: S.set, chapter: S.chapter });
  } catch (e) { notice(e.message); return; }
  if (!data.questions.length) {
    show("menu");
    notice("no questions match that selection.");
    return;
  }
  S.sessionMsg = null;
  S.quiz = {
    pool: data.questions, i: 0, asked: 0, correct: 0, mode,
    focus: data.focus, stage: "answering", selected: new Set(), graded: null,
  };
  renderQuestion();
}

function renderQuestion() {
  const qz = S.quiz;
  const q = qz.pool[qz.i];

  $("q-counter").textContent = `${qz.i + 1} / ${qz.pool.length}`;
  $("q-track").style.width = `${(100 * qz.i) / qz.pool.length}%`;
  $("q-meta").textContent = `#${q.id} · ${q.topics.join(" / ")}`;

  const focus = $("focus-note");
  if (qz.mode === "weak" && qz.i === 0 && qz.stage === "answering") {
    focus.hidden = false;
    focus.textContent = qz.focus.length
      ? `focusing on: ${qz.focus.join(", ")}`
      : "not enough data yet — using the whole bank.";
  } else {
    focus.hidden = true;
  }

  $("q-text").textContent = q.question;
  const multi = $("q-multi");
  multi.hidden = !q.select_n;
  if (q.select_n) multi.textContent = `(select ${q.select_n} answers)`;

  const opts = $("q-options");
  opts.replaceChildren();
  q.options.forEach((text, i) => {
    const li = el("li");
    const btn = el("button", "option");
    btn.dataset.index = i;
    btn.setAttribute("aria-pressed", String(qz.selected.has(i)));
    btn.append(el("span", "bubble", letter(i)), el("span", "option-text", text));
    if (qz.stage === "answering") {
      btn.addEventListener("click", () => toggleOption(i));
    } else {
      btn.disabled = true;
    }
    li.append(btn);
    opts.append(li);
  });

  $("save-warn").hidden = true;
  if (qz.stage === "graded") {
    paintGrading();
  } else {
    $("q-verdict").hidden = true;
    $("q-explanation").hidden = true;
    renderQuizActions();
  }
  show("quiz");
}

function toggleOption(i) {
  const qz = S.quiz;
  if (qz.stage !== "answering") return;
  if (qz.selected.has(i)) qz.selected.delete(i);
  else qz.selected.add(i);
  const btn = $("q-options").querySelector(`[data-index="${i}"]`);
  btn.setAttribute("aria-pressed", String(qz.selected.has(i)));
  const check = $("check-btn");
  if (check) check.disabled = !qz.selected.size;
}

function renderQuizActions() {
  const qz = S.quiz;
  const box = $("quiz-actions");
  box.replaceChildren();
  const tut = S.info.tutor_on;

  if (qz.stage === "answering") {
    const check = el("button", "btn primary", "check answer");
    check.id = "check-btn";
    check.disabled = !qz.selected.size;
    check.addEventListener("click", checkAnswer);
    box.append(check);
    box.append(actionBtn("skip", skipQuestion));
    if (tut) box.append(actionBtn("ask the tutor", () => openTutorForQuestion(false)));
  } else {
    const next = el("button", "btn primary", qz.i + 1 < qz.pool.length ? "next question" : "finish");
    next.id = "next-btn";
    next.addEventListener("click", nextQuestion);
    box.append(next);
    if (tut) box.append(actionBtn("ask the tutor", () => openTutorForQuestion(true)));
  }
  box.append(actionBtn("menu", leaveQuiz));
}

function actionBtn(label, run) {
  const b = el("button", "btn quiet", label);
  b.addEventListener("click", run);
  return b;
}

async function checkAnswer() {
  const qz = S.quiz;
  if (!qz.selected.size) return;
  const q = qz.pool[qz.i];
  const letters = [...qz.selected].sort((a, b) => a - b).map(letter).join("");
  let res;
  try {
    res = await api("/api/answer", { id: q.id, answer: letters, chapter: S.chapter });
  } catch (e) { notice(e.message); return; }

  qz.asked += 1;
  if (res.correct) qz.correct += 1;
  qz.stage = "graded";
  qz.graded = res;
  renderQuestion();
  if (res.warning) {
    $("save-warn").textContent = "warning: " + res.warning;
    $("save-warn").hidden = false;
  }
  const next = $("next-btn");
  if (next) next.focus();
}

function paintGrading() {
  const qz = S.quiz;
  const res = qz.graded;
  const correctIdx = new Set(res.correct_letters.map((l) => l.charCodeAt(0) - 65));

  for (const btn of $("q-options").querySelectorAll(".option")) {
    const i = Number(btn.dataset.index);
    const picked = qz.selected.has(i);
    btn.setAttribute("aria-pressed", "false");
    if (correctIdx.has(i)) {
      btn.classList.add("is-right");
      btn.append(el("span", "mark right", picked ? "✓" : "✓ answer"));
    } else if (picked) {
      btn.classList.add("is-wrong");
      btn.append(el("span", "mark wrong", "✗"));
    } else {
      btn.classList.add("is-faded");
    }
  }

  const verdict = $("q-verdict");
  verdict.hidden = false;
  const letters = res.correct_letters.join(", ");
  verdict.className = "verdict " + (res.correct ? "right" : "wrong");
  verdict.textContent = res.correct
    ? `✓ correct! (${letters})`
    : `✗ incorrect. correct answer: ${letters}`;

  const expl = $("q-explanation");
  expl.hidden = !res.explanation;
  if (res.explanation) expl.textContent = res.explanation;

  renderQuizActions();
  setFootKeys("quiz");
}

function skipQuestion() {
  advance();
}

function nextQuestion() {
  advance();
}

function advance() {
  const qz = S.quiz;
  if (qz.i + 1 < qz.pool.length) {
    qz.i += 1;
    qz.stage = "answering";
    qz.selected = new Set();
    qz.graded = null;
    renderQuestion();
  } else {
    endSession("done");
  }
}

function leaveQuiz() {
  endSession("menu");
}

async function endSession(dest) {
  const qz = S.quiz;
  S.quiz = null;
  if (qz.asked > 0) {
    try {
      const res = await api("/api/session", { asked: qz.asked, correct: qz.correct, chapter: S.chapter });
      if (res.warning) notice("warning: " + res.warning);
    } catch (e) { notice(e.message); }
    const pct = Math.round((100 * qz.correct) / qz.asked);
    S.sessionMsg = `session: ${qz.correct}/${qz.asked} correct (${pct}%)`;
  } else {
    S.sessionMsg = null;
  }

  if (dest === "done" && qz.asked > 0) {
    $("done-line").textContent = S.sessionMsg;
    show("done");
  } else {
    backToMenu();
  }
}

/* ── Dashboard ───────────────────────────────────────────── */

async function showDashboard() {
  const params = new URLSearchParams();
  if (S.chapter) params.set("chapter", S.chapter);
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

/* ── Tutor ───────────────────────────────────────────────── */

function openTutorForQuestion(afterAnswer) {
  const qz = S.quiz;
  const q = qz.pool[qz.i];
  if (afterAnswer) {
    const picked = [...qz.selected].sort((a, b) => a - b).map(letter).join(", ");
    openTutor({ qid: q.id, stage: "reveal", correct: qz.graded.correct, picked }, "quiz");
  } else {
    openTutor({ qid: q.id, stage: "hint" }, "quiz");
  }
}

function openTutor(ctx, returnTo) {
  S.tutor = {
    history: [],
    qid: ctx ? ctx.qid : null,
    stage: ctx ? ctx.stage : "chat",
    correct: ctx ? ctx.correct : null,
    picked: ctx ? ctx.picked : "",
    returnTo,
    busy: false,
  };
  $("chat-log").replaceChildren();
  $("tutor-context").textContent = ctx
    ? (ctx.stage === "hint"
        ? `about question #${ctx.qid} — hints only, no spoilers.`
        : `about question #${ctx.qid}.`)
    : "general study chat — the tutor knows your progress.";
  show("tutor");
  $("chat-input").focus();
}

function closeTutor() {
  const dest = S.tutor.returnTo;
  S.tutor = null;
  if (dest === "quiz" && S.quiz) renderQuestion();
  else show("menu");
}

function chatMsg(who, cls) {
  const wrap = el("div", "msg " + cls);
  wrap.append(el("span", "msg-who", who + " ›"));
  const body = el("div", "msg-body");
  wrap.append(body);
  $("chat-log").append(wrap);
  return body;
}

async function sendToTutor(text) {
  const t = S.tutor;
  t.busy = true;
  chatMsg("you", "you").textContent = text;
  const body = chatMsg("tutor", "tutor");
  body.textContent = "…";

  let res;
  try {
    res = await fetch("/api/tutor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        history: t.history,
        question_id: t.qid,
        stage: t.stage,
        correct: t.correct,
        picked: t.picked,
        set: S.set,
        chapter: S.chapter,
      }),
    });
  } catch (e) {
    body.textContent = `tutor error: ${e.message}`;
    t.busy = false;
    return;
  }
  if (!res.ok) {
    if (res.status === 401) { showAuth(); return; }
    const data = await res.json().catch(() => ({}));
    body.textContent = data.error || `tutor error (${res.status})`;
    t.busy = false;
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let full = "";
  body.textContent = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    full += decoder.decode(value, { stream: true });
    body.textContent = full;
    body.scrollIntoView({ block: "end" });
  }
  t.history.push({ role: "user", content: text });
  t.history.push({ role: "assistant", content: full });
  t.busy = false;
}

$("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text || S.tutor.busy) return;
  input.value = "";
  if (["back", "exit", "quit", "q"].includes(text.toLowerCase())) {
    closeTutor();
    return;
  }
  sendToTutor(text);
});

$("tutor-back").addEventListener("click", closeTutor);

/* ── Set switcher ────────────────────────────────────────── */

$("set-select").addEventListener("change", (e) => {
  S.set = e.target.value || null;
  S.sessionMsg = null;
  backToMenu();
});

/* ── Home link ───────────────────────────────────────────── */

$("home-link").addEventListener("click", goHome);

/* ── Keyboard ────────────────────────────────────────────── */

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea") || e.metaKey || e.ctrlKey || e.altKey) {
    if (e.key === "Escape" && S.view === "tutor") closeTutor();
    return;
  }
  const k = e.key.toLowerCase();

  if (S.view === "chapters") {
    const i = Number(k) - 1;
    if (Number.isInteger(i) && i >= 0 && i < S.chapters.length) {
      selectChapter(S.chapters[i].slug);
    }
  } else if (S.view === "menu") {
    const item = MENU_STUDY.find((m) => m.key === k);
    if (item) { e.preventDefault(); item.run(); }
    else if (k === "6") showDashboard();
    else if (k === "7" && S.info.tutor_on) openTutor(null, "menu");
    else if (k === "c" && S.chapters.length > 1) goHome();
    else if (k === "s" && S.info.sets.length) $("set-select").focus();
  } else if (S.view === "topics") {
    if (k === "m" || k === "escape") show("menu");
  } else if (S.view === "dashboard") {
    if (k === "m" || k === "escape") show("menu");
  } else if (S.view === "done") {
    if (k === "enter" || k === "m" || k === "escape") backToMenu();
  } else if (S.view === "tutor") {
    if (k === "escape") closeTutor();
    else $("chat-input").focus();
  } else if (S.view === "quiz" && S.quiz) {
    const qz = S.quiz;
    if (qz.stage === "answering") {
      if (k === "enter") { e.preventDefault(); checkAnswer(); }
      else if (k === "s") skipQuestion();
      else if (k === "m") leaveQuiz();
      else if (k === "t" && S.info.tutor_on) openTutorForQuestion(false);
      else if (k >= "a" && k <= "z") {
        const i = k.charCodeAt(0) - 97;
        if (i < qz.pool[qz.i].options.length) toggleOption(i);
      }
    } else {
      if (k === "enter") { e.preventDefault(); nextQuestion(); }
      else if (k === "m") leaveQuiz();
      else if (k === "t" && S.info.tutor_on) openTutorForQuestion(true);
    }
  }
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action='menu']");
  if (btn) backToMenu();
});

/* ── Boot ────────────────────────────────────────────────── */

(async () => {
  try {
    const auth = await api("/api/auth");
    S.inviteRequired = auth.invite_required;
    if (auth.signed_in) await signedIn(auth.username);
    else showAuth();
  } catch (e) {
    showAuth();
    notice("could not reach the server: " + e.message);
  }
})();
