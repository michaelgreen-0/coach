import { S } from "./state.js";

// main.js registers showAuth here so a mid-session 401 can bounce back to sign-in
// without api.js having to import a feature module.
let unauthorized = null;
export function onUnauthorized(fn) { unauthorized = fn; }

export async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && S.view !== "auth" && unauthorized) unauthorized();
    const err = new Error(data.error || `request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}
