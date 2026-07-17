import { S } from "../core/state.js";
import { $ } from "../core/dom.js";
import { show } from "../core/view.js";
import { api } from "../core/api.js";
import { tocRow } from "../core/components.js";
import { backToMenu } from "./menu.js";

export async function loadSubjects() {
  const data = await api("/api/subjects");
  S.subjects = data.subjects;
  if (S.subjects.length === 1) {
    selectSubject(S.subjects[0].slug);
  } else {
    renderSubjects();
  }
}

export function renderSubjects() {
  const list = $("subject-list");
  list.replaceChildren();
  S.subjects.forEach((subj, i) => {
    list.append(tocRow(String(i + 1), subj.name, null,
      `${subj.question_count} questions`, () => selectSubject(subj.slug)));
  });
  show("subjects");
}

export function selectSubject(slug) {
  S.subject = slug;
  S.set = null;
  S.sessionMsg = null;
  backToMenu();
}

export function goHome() {
  if (S.subjects.length > 1) {
    S.sessionMsg = null;
    renderSubjects();
  } else if (S.subject) {
    backToMenu();
  }
}
