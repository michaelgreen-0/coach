import { S, VIEWS } from "./state.js";
import { $, letter } from "./dom.js";

export function show(view) {
  S.view = view;
  for (const v of VIEWS) $("view-" + v).hidden = v !== view;
  $("notice").hidden = true;
  setFootKeys(view);
}

export function notice(text) {
  const n = $("notice");
  n.textContent = text;
  n.hidden = false;
}

export function setFootKeys(view) {
  const f = $("foot-keys");
  const tut = S.info && S.info.tutor_on && S.info.signed_in;
  if (view === "quiz" && S.quiz) {
    const last = letter(S.quiz.pool[S.quiz.i].options.length - 1).toLowerCase();
    f.textContent = S.quiz.stage === "answering"
      ? `a–${last} select · enter check · s skip${tut ? " · t tutor" : ""} · m menu`
      : `enter next${tut ? " · t tutor" : ""} · m menu`;
  } else {
    f.textContent = "";
  }
}
