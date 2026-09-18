/* Thin API client. The base URL is baked at build time by Amplify from
   VITE_API_BASE_URL; with nothing set it talks to the local Lambda shim
   (backend/local_server.py), so the same frontend runs in both places. */
const BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch (cause) {
    throw new Error(`Could not reach the BreakFix API at ${BASE}. Is the backend running?`);
  }

  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`The API returned a malformed response (HTTP ${response.status}).`);
  }
  if (!response.ok) {
    const err = new Error(payload.error || `Request failed with HTTP ${response.status}.`);
    err.status = response.status;
    err.payload = payload;
    throw err;
  }
  return payload;
}

export const api = {
  baseUrl: BASE,
  listChallenges: () => request('/challenges'),
  startSession: (challengeId, displayName) =>
    request('/sessions', {
      method: 'POST',
      body: JSON.stringify({ challenge_id: challengeId, user_display_name: displayName }),
    }),
  submitFix: (sessionId, submittedCode) =>
    request(`/sessions/${encodeURIComponent(sessionId)}/submit`, {
      method: 'POST',
      body: JSON.stringify({ submitted_code: submittedCode }),
    }),
  leaderboard: () => request('/leaderboard'),
};

export function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}
