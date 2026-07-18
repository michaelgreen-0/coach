import { S } from "../core/state.js";
import { $, el, letter } from "../core/dom.js";
import { show, notice, setFootKeys } from "../core/view.js";
import { api } from "../core/api.js";
import { backToMenu } from "./menu.js";
import { openTutorForQuestion } from "./tutor.js";

export async function startQuiz(mode, topic = null) {
  let data;
  try {
    data = await api("/api/quiz", { mode, topic, set: S.set, subject: S.subject });
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

export function renderQuestion() {
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

export function toggleOption(i) {
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
  const tut = S.info.tutor_on && S.info.signed_in;

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

export async function checkAnswer() {
  const qz = S.quiz;
  if (!qz.selected.size) return;
  const q = qz.pool[qz.i];
  const letters = [...qz.selected].sort((a, b) => a - b).map(letter).join("");
  let res;
  try {
    res = await api("/api/answer", { id: q.id, answer: letters, subject: S.subject });
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

export function skipQuestion() {
  advance();
}

export function nextQuestion() {
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

export function leaveQuiz() {
  endSession("menu");
}

async function endSession(dest) {
  const qz = S.quiz;
  S.quiz = null;
  if (qz.asked > 0) {
    try {
      const res = await api("/api/session", { asked: qz.asked, correct: qz.correct, subject: S.subject });
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
