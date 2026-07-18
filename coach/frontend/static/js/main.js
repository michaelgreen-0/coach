import { S } from "./core/state.js";
import { $ } from "./core/dom.js";
import { notice } from "./core/view.js";
import { api, onUnauthorized } from "./core/api.js";
import { showAuth, enterApp } from "./features/auth.js";
import { goHome } from "./features/subjects.js";
import "./keys.js";

onUnauthorized(showAuth);
$("home-link").addEventListener("click", goHome);

(async () => {
  try {
    const auth = await api("/api/auth");
    S.username = auth.signed_in ? auth.username : null;
    await enterApp();  // browse works signed in or out; the tutor needs an account
  } catch (e) {
    showAuth();
    notice("could not reach the server: " + e.message);
  }
})();
