export const S = {
  username: null,  // signed-in user
  authMode: "login",
  subjects: [],    // /api/subjects payload
  subject: null,   // active subject slug
  info: null,      // /api/state payload
  set: null,       // active question set, null = all
  quiz: null,      // {pool, i, asked, correct, mode, focus, stage, selected, graded}
  tutor: null,     // {history, qid, stage, correct, picked, returnTo}
  view: "auth",
  sessionMsg: null,
};

export const VIEWS = ["auth", "subjects", "menu", "topics", "quiz", "done", "dashboard", "tutor"];
