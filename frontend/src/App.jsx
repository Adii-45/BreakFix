import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { api } from './api.js';
import ChallengeList from './components/ChallengeList.jsx';

// CodeMirror is the bulk of the bundle and is only needed once a challenge has
// started, so it is split out of the initial load. The home screen paints fast.
const EditorScreen = lazy(() => import('./components/EditorScreen.jsx'));
import ResultsScreen from './components/ResultsScreen.jsx';
import Leaderboard from './components/Leaderboard.jsx';

const NAME_KEY = 'breakfix.displayName';

export default function App() {
  const [view, setView] = useState('home');           // home | editor | results
  const [displayName, setDisplayName] = useState(() => localStorage.getItem(NAME_KEY) || '');
  const [challenges, setChallenges] = useState([]);
  const [loadingChallenges, setLoadingChallenges] = useState(true);
  const [leaderboard, setLeaderboard] = useState([]);
  const [loadingLeaderboard, setLoadingLeaderboard] = useState(true);
  const [session, setSession] = useState(null);
  const [result, setResult] = useState(null);
  const [startingId, setStartingId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const refreshLeaderboard = useCallback(async () => {
    setLoadingLeaderboard(true);
    try {
      const data = await api.leaderboard();
      setLeaderboard(data.leaderboard || []);
    } catch {
      setLeaderboard([]);
    } finally {
      setLoadingLeaderboard(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.listChallenges();
        setChallenges(data.challenges || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoadingChallenges(false);
      }
    })();
    refreshLeaderboard();
  }, [refreshLeaderboard]);

  useEffect(() => {
    localStorage.setItem(NAME_KEY, displayName);
  }, [displayName]);

  const startChallenge = useCallback(async (challenge) => {
    setError('');
    setStartingId(challenge.challenge_id);
    try {
      const started = await api.startSession(challenge.challenge_id, displayName.trim() || 'Anonymous');
      setSession(started);
      setResult(null);
      setView('editor');
    } catch (err) {
      setError(err.message);
    } finally {
      setStartingId(null);
    }
  }, [displayName]);

  const submitFix = useCallback(async (code) => {
    if (!session) return;
    setSubmitting(true);
    setError('');
    try {
      const submitted = await api.submitFix(session.session_id, code);
      setResult(submitted);
      setView('results');
      refreshLeaderboard();
    } catch (err) {
      // A 409 means this session was already scored; show that result rather
      // than stranding the student on the editor screen.
      if (err.status === 409 && err.payload?.result) {
        setResult(err.payload.result);
        setView('results');
        refreshLeaderboard();
      } else {
        setError(err.message);
      }
    } finally {
      setSubmitting(false);
    }
  }, [session, refreshLeaderboard]);

  const goHome = useCallback(() => {
    setView('home');
    setSession(null);
    setResult(null);
    setError('');
    refreshLeaderboard();
  }, [refreshLeaderboard]);

  const challengeLabel = session
    ? `${session.repo_name} · ${session.function_name}()`
    : result?.challenge_id || '';

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span>Break<em>Fix</em></span>
          <span className="tag">AI-judged debugging</span>
        </div>
        <span className="spacer" />
        {view !== 'home' && (
          <button type="button" className="btn btn-ghost" onClick={goHome}>
            Challenges
          </button>
        )}
      </header>

      <main>
        {view === 'home' && (
          <>
            <div className="page-head">
              <h1>Find the bug. Fix it. Get judged on how.</h1>
              <p>
                Every challenge is a real function from a real open-source repository with one bug injected by an
                AI agent. Your fix is verified by hidden unit tests that actually execute your code, then a second
                agent scores your debugging process.
              </p>
            </div>

            {error && <div className="banner" role="alert">{error}</div>}

            <div className="layout-split">
              <div>
                <div className="field" style={{ maxWidth: 340, marginBottom: 22 }}>
                  <label htmlFor="display-name">Display name (for the leaderboard)</label>
                  <input
                    id="display-name"
                    className="input"
                    value={displayName}
                    maxLength={32}
                    placeholder="Anonymous"
                    onChange={(event) => setDisplayName(event.target.value)}
                  />
                </div>

                {loadingChallenges ? (
                  <div className="center-note"><span className="spinner" /> Loading challenges…</div>
                ) : (
                  <ChallengeList
                    challenges={challenges}
                    onSelect={startChallenge}
                    startingId={startingId}
                    disabled={Boolean(startingId)}
                  />
                )}
              </div>
              <Leaderboard entries={leaderboard} loading={loadingLeaderboard} />
            </div>
          </>
        )}

        {view === 'editor' && session && (
          <>
            <div className="page-head">
              <h1>{session.function_name}()</h1>
              <p>From {session.repo_name}. One bug was injected into this function — find it and fix it.</p>
            </div>
            <Suspense fallback={<div className="center-note"><span className="spinner" /> Loading editor…</div>}>
              <EditorScreen
                session={session}
                onSubmit={submitFix}
                submitting={submitting}
                error={error}
                onAbandon={goHome}
              />
            </Suspense>
          </>
        )}

        {view === 'results' && result && (
          <>
            <div className="page-head">
              <h1>Results</h1>
              <p>Correctness came from executing hidden tests. The score and feedback came from the Evaluator Agent.</p>
            </div>
            <ResultsScreen result={result} challengeLabel={challengeLabel} onRestart={goHome} />
            <div style={{ marginTop: 24, maxWidth: 420 }}>
              <Leaderboard entries={leaderboard} loading={loadingLeaderboard} />
            </div>
          </>
        )}
      </main>

      <footer className="foot">
        <span className="aws">Bedrock · Lambda · API Gateway · DynamoDB · Amplify Hosting</span>
        <span>·</span>
        <span>Correctness is decided by real test execution, never by an LLM.</span>
      </footer>
    </div>
  );
}
