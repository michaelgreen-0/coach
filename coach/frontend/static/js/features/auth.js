import { S } from "../core/state.js";
import { $ } from "../core/dom.js";
import { show } from "../core/view.js";
import { api } from "../core/api.js";
import { loadSubjects, goHome } from "./subjects.js";

export function showAuth() {
  S.username = null;
  $("user-chip").hidden = true;
  $("sign-in").hidden = true;  // the header entry point is redundant while the form is up
  $("set-switch").hidden = true;
  setAuthMode(S.authMode);
  $("auth-cancel").hidden = S.subjects.length === 0;
  show("auth");
  $("auth-username").focus();
}

// Land in the app for the current signed-in-or-not state.
export async function enterApp() {
  renderUserChip();
  await loadSubjects();
}

function setAuthMode(mode) {
  S.authMode = mode;
  const login = mode === "login";
  $("auth-submit").textContent = login ? "sign in" : "create account";
  $("auth-toggle").textContent = login
    ? "new here? create an account"
    : "have an account? sign in";
  $("auth-password").autocomplete = login ? "current-password" : "new-password";
  $("auth-error").hidden = true;
}

function renderUserChip() {
  const signedIn = !!S.username;
  $("user-chip").hidden = !signedIn;
  $("sign-in").hidden = signedIn;
  if (signedIn) $("user-name").textContent = S.username + " ·";
}

export async function signedIn(username) {
  S.username = username;
  await enterApp();
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
      : await api("/api/register", { username, password });
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

$("sign-in").addEventListener("click", showAuth);

$("auth-cancel").addEventListener("click", () => {
  renderUserChip();
  goHome();
});

$("sign-out").addEventListener("click", async () => {
  try { await api("/api/logout", {}); } catch { /* signing out locally regardless */ }
  S.username = null;
  S.subject = null;
  S.set = null;
  S.quiz = null;
  S.sessionMsg = null;
  S.authMode = "login";
  await enterApp();  // stay in the app as an anonymous visitor
});
