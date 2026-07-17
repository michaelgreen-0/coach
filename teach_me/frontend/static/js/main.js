import { S } from "./core/state.js";
import { $ } from "./core/dom.js";
import { notice } from "./core/view.js";
import { api, onUnauthorized } from "./core/api.js";
import { showAuth, signedIn } from "./features/auth.js";
import { goHome } from "./features/subjects.js";
import "./keys.js";

onUnauthorized(showAuth);
$("home-link").addEventListener("click", goHome);

(async () => {
  try {
    const auth = await api("/api/auth");
    S.inviteRequired = auth.invite_required;
    if (auth.signed_in) await signedIn(auth.username);
    else showAuth();
  } catch (e) {
    showAuth();
    notice("could not reach the server: " + e.message);
  }
})();
