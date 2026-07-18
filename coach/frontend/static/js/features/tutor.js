import { S } from "../core/state.js";
import { $, el, letter } from "../core/dom.js";
import { show } from "../core/view.js";
import { showAuth } from "./auth.js";
import { renderQuestion } from "./quiz.js";

export function openTutorForQuestion(afterAnswer) {
  const qz = S.quiz;
  const q = qz.pool[qz.i];
  if (afterAnswer) {
    const picked = [...qz.selected].sort((a, b) => a - b).map(letter).join(", ");
    openTutor({ qid: q.id, stage: "reveal", correct: qz.graded.correct, picked }, "quiz");
  } else {
    openTutor({ qid: q.id, stage: "hint" }, "quiz");
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
  context.hidden = !ctx;
  if (ctx) {
    context.textContent = ctx.stage === "hint"
      ? `about question #${ctx.qid} — hints only, no spoilers.`
      : `about question #${ctx.qid}.`;
  }
  show("tutor");
  $("chat-input").focus();
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
