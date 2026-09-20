/** Per-tab persistence so a page refresh does not lose an attempt.
 *  The API has no GET /sessions/{id}, so the session and result are kept client-side.
 *  Storage can be unavailable (private mode, quota) -- every call degrades to a no-op. */
const key = (kind, id) => `breakfix:${kind}:${id}`;

export function save(kind, id, value) {
  try {
    sessionStorage.setItem(key(kind, id), JSON.stringify(value));
  } catch {
    /* storage unavailable: the attempt simply is not restorable */
  }
}

export function load(kind, id) {
  try {
    const raw = sessionStorage.getItem(key(kind, id));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
