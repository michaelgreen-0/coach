import { S } from "../core/state.js";
import { $, el, letter } from "../core/dom.js";
import { show } from "../core/view.js";
import { showAuth } from "./auth.js";
import { renderQuestion } from "./quiz.js";

export function openTutorForQuestion(afterAnswer) {
  const qz = S.quiz;
  const q = qz.pool[qz.i];
  const pickedIdx = [...qz.selected].sort((a, b) => a - b);
  const picked = pickedIdx.map(letter).join(", ");
  const shared = { qid: q.id, question: q.question, options: q.options, pickedIdx, picked };
  if (afterAnswer) {
    const correctIdx = qz.graded.correct_letters.map((l) => l.charCodeAt(0) - 65);
    openTutor({ ...shared, stage: "reveal", correct: qz.graded.correct, correctIdx }, "quiz");
  } else {
    openTutor({ ...shared, stage: "hint" }, "quiz");
  }
}

export function openTutor(ctx, returnTo) {
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
  const context = $("tutor-context");
  const card = $("tutor-question");
  card.replaceChildren();
  const hasQuestion = !!(ctx && ctx.question);
  context.hidden = !ctx;
  card.hidden = !hasQuestion;
  if (ctx) {
    context.textContent = ctx.stage === "hint"
      ? `about question #${ctx.qid} — hints only, no spoilers.`
      : `about question #${ctx.qid}.`;
    if (hasQuestion) renderTutorQuestion(card, ctx);
  }
  show("tutor");
  $("chat-input").focus();
}

// Mirror the quiz's question + grading so it stays visible while chatting.
// Before answering (hint) the correct answer is withheld — no spoilers.
function renderTutorQuestion(card, ctx) {
  card.append(el("p", "tq-text", ctx.question));
  const list = el("ol", "tq-options");
  const reveal = ctx.stage !== "hint";
  const correct = new Set(reveal ? ctx.correctIdx : []);
  const picked = new Set(ctx.pickedIdx);
  ctx.options.forEach((text, i) => {
    const row = el("li", "tq-row");
    row.append(el("span", "bubble", letter(i)), el("span", "option-text", text));
    if (reveal && correct.has(i)) {
      row.classList.add("is-right");
      row.append(el("span", "tq-mark right", picked.has(i) ? "✓ your pick" : "✓ answer"));
    } else if (reveal && picked.has(i)) {
      row.classList.add("is-wrong");
      row.append(el("span", "tq-mark wrong", "✗ your pick"));
    } else if (picked.has(i)) {
      row.append(el("span", "tq-mark pick", "your pick"));
    } else if (reveal) {
      row.classList.add("is-faded");
    }
    list.append(row);
  });
  card.append(list);
}

export function closeTutor() {
  const dest = S.tutor.returnTo;
  S.tutor = null;
  if (dest === "quiz" && S.quiz) renderQuestion();
  else show("menu");
}

const SENT = String.fromCharCode(0);
const SENT_RE = new RegExp(SENT + "(\\d+)" + SENT, "g");

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
}

function renderMarkdown(text) {
  const code = [];
  const stashed = escapeHtml(text).replace(/`([^`]+)`/g, (_, c) => {
    code.push(c);
    return SENT + (code.length - 1) + SENT;
  });
  return stashed
    .replace(/\*\*([^\n]+?)\*\*/g, "<strong>$1</strong>")
    .replace(SENT_RE, (_, i) => "<code>" + code[+i] + "</code>");
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
        subject: S.subject,
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
    body.innerHTML = renderMarkdown(full);
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
