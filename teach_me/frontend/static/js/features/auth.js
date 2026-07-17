import { S } from "../core/state.js";
import { $ } from "../core/dom.js";
import { show } from "../core/view.js";
import { api } from "../core/api.js";
import { loadSubjects } from "./subjects.js";

export function showAuth() {
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

export async function signedIn(username) {
  S.username = username;
  renderUserChip();
  await loadSubjects();
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
  S.subject = null;
  S.subjects = [];
  S.set = null;
  S.quiz = null;
  S.sessionMsg = null;
  S.authMode = "login";
  showAuth();
});
