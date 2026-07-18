import { S } from "./core/state.js";
import { $ } from "./core/dom.js";
import { show } from "./core/view.js";
import { selectSubject, goHome } from "./features/subjects.js";
import { MENU_STUDY, backToMenu } from "./features/menu.js";
import { showDashboard } from "./features/dashboard.js";
import { openTutor, openTutorForQuestion, closeTutor } from "./features/tutor.js";
import { checkAnswer, skipQuestion, nextQuestion, leaveQuiz, toggleOption } from "./features/quiz.js";

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea") || e.metaKey || e.ctrlKey || e.altKey) {
    if (e.key === "Escape" && S.view === "tutor") closeTutor();
    return;
  }
  const k = e.key.toLowerCase();

  if (S.view === "subjects") {
    const i = Number(k) - 1;
    if (Number.isInteger(i) && i >= 0 && i < S.subjects.length) {
      selectSubject(S.subjects[i].slug);
    }
  } else if (S.view === "menu") {
    const item = MENU_STUDY.find((m) => m.key === k);
    if (item && (!item.needsAuth || S.info.signed_in)) { e.preventDefault(); item.run(); }
    else if (k === "6" && S.info.signed_in) showDashboard();
    else if (k === "7" && S.info.tutor_on && S.info.signed_in) openTutor(null, "menu");
    else if (k === "c" && S.subjects.length > 1) goHome();
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
      else if (k === "t" && S.info.tutor_on && S.info.signed_in) openTutorForQuestion(false);
      else if (k >= "a" && k <= "z") {
        const i = k.charCodeAt(0) - 97;
        if (i < qz.pool[qz.i].options.length) toggleOption(i);
      }
    } else {
      if (k === "enter") { e.preventDefault(); nextQuestion(); }
      else if (k === "m") leaveQuiz();
      else if (k === "t" && S.info.tutor_on && S.info.signed_in) openTutorForQuestion(true);
    }
  }
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action='menu']");
  if (btn) backToMenu();
});
