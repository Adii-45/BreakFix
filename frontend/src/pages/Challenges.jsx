import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { api, NO_DATA, formatSeconds } from '../api.js';
import { useApp } from '../store.jsx';
import { SkeletonChallengeCard, SkeletonRows } from '../components/Skeleton.jsx';
import { LeaderboardEmpty, LeaderboardList } from '../components/LeaderboardRows.jsx';
import { springTactile, EASE } from '../motion.js';

export default function Challenges() {
  const navigate = useNavigate();
  const { challenges, stats, leaderboard, displayName, setDisplayName, error } = useApp();
  const [query, setQuery] = useState('');
  const [startingId, setStartingId] = useState(null);
  const [startError, setStartError] = useState('');

  const loading = challenges === null;

  const filtered = useMemo(() => {
    if (!challenges) return [];
    const q = query.trim().toLowerCase();
    if (!q) return challenges;
    return challenges.filter((c) =>
      `${c.function_name} ${c.repo_name} ${c.language} ${c.difficulty}`.toLowerCase().includes(q));
  }, [challenges, query]);

  const start = useCallback(async (challenge) => {
    setStartError('');
    setStartingId(challenge.challenge_id);
    try {
      const session = await api.startSession(challenge.challenge_id, displayName.trim() || 'Anonymous');
      navigate(`/challenges/${session.session_id}`, { state: { session } });
    } catch (err) {
      setStartError(err.message);
      setStartingId(null);
    }
  }, [displayName, navigate]);

  return (
    <div className="shell section-sm">
      <div className="stack gap-md" style={{ marginBottom: 'var(--s-xl)' }}>
        <div className="row gap-sm wrap">
          <span className="eyebrow"><span className="dot dot-live" style={{ color: 'var(--success)' }} /> Seeded challenge set</span>
          {stats && (
            <span className="chip">
              {stats.hidden_tests_total} hidden tests · {stats.repos_covered} repos
            </span>
          )}
        </div>
        <h1 className="t-headline" style={{ margin: 0 }}>Active challenges</h1>
        <p className="t-body-lg text-dim measure" style={{ margin: 0 }}>
          Each one is a real function with a single injected bug. Your fix is validated by hidden unit
          tests that actually execute it inside a sandbox — then reviewed for how you got there.
        </p>
      </div>

      {(error || startError) && (
        <div className="banner banner-error" style={{ marginBottom: 'var(--s-lg)' }} role="alert">
          {startError || error}
        </div>
      )}

      <div className="challenge-layout">
        <div className="stack gap-lg">
          <div className="row gap-md wrap">
            <div style={{ flex: 1, minWidth: 220 }}>
              <input
                className="input input-mono"
                placeholder="Filter by function, repo or language…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Filter challenges"
              />
            </div>
            <div style={{ width: 200 }}>
              <input
                className="input"
                placeholder="Display name"
                maxLength={32}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                aria-label="Display name for the leaderboard"
              />
            </div>
          </div>

          {loading ? (
            <div className="challenge-grid">
              {Array.from({ length: 4 }).map((_, i) => <SkeletonChallengeCard key={i} />)}
            </div>
          ) : filtered.length === 0 ? (
            <div className="card">
              <div className="empty-state">
                <span className="icon" aria-hidden="true">⌕</span>
                <span className="t-body" style={{ color: 'var(--text-dim)' }}>
                  {challenges.length === 0
                    ? 'No challenges are seeded yet.'
                    : `Nothing matches “${query}”.`}
                </span>
                <span className="t-body-sm text-muted">
                  {challenges.length === 0
                    ? 'Run the authoring pipeline in seed-data/ to populate the catalogue.'
                    : 'Try a different function or repository name.'}
                </span>
              </div>
            </div>
          ) : (
            <div className="challenge-grid">
              {filtered.map((challenge, i) => (
                <ChallengeCard
                  key={challenge.challenge_id}
                  challenge={challenge}
                  stat={stats?.per_challenge?.[challenge.challenge_id]}
                  index={i}
                  starting={startingId === challenge.challenge_id}
                  disabled={Boolean(startingId)}
                  onStart={() => start(challenge)}
                />
              ))}
            </div>
          )}

          {!loading && filtered.length > 0 && (
            <p className="t-code-sm text-muted" style={{ margin: 0 }}>
              Showing {filtered.length} of {challenges.length} seeded {challenges.length === 1 ? 'challenge' : 'challenges'}.
            </p>
          )}
        </div>

        {/* ------------------------------------------------------- side rail */}
        <aside className="stack gap-lg challenge-rail">
          <section className="card">
            <div className="card-head">
              <span className="t-label text-dim">Top scores</span>
              <span className="spacer" />
              {leaderboard !== null && leaderboard.length > 0 && (
                <span className="chip chip-accent">{leaderboard.length} scored</span>
              )}
            </div>
            <div className="card-body" style={{ paddingTop: leaderboard?.length ? 8 : 16 }}>
              {leaderboard === null
                ? <SkeletonRows rows={3} height={38} />
                : leaderboard.length === 0
                  ? <LeaderboardEmpty />
                  : <LeaderboardList entries={leaderboard.slice(0, 5)} highlightName={displayName} />}
            </div>
          </section>

          <section className="card">
            <div className="card-head"><span className="t-label text-dim">How you are scored</span></div>
            <div className="card-body stack gap-md">
              <ScoreRow
                title="Correctness"
                tone="var(--success)"
                body="Hidden unit tests execute your submission in a sandbox. Passing every test is the verdict — a boolean, not an opinion."
                foot="tests_passed == tests_total"
              />
              <hr className="rule" />
              <ScoreRow
                title="Quality score (0–100)"
                tone="var(--accent)"
                body="The Evaluator Agent reads your diff against the ground truth and rates how targeted the fix was. It is handed the test result and cannot contradict it."
                foot="Bedrock · PRD rubric §8.2"
              />
              <div className="banner banner-note">
                A minimal, targeted fix that passes scores highest. A broad rewrite that happens to pass
                scores lower.
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function ScoreRow({ title, body, foot, tone }) {
  return (
    <div className="stack gap-xs">
      <div className="row gap-sm">
        <span className="dot" style={{ color: tone }} />
        <span className="t-body" style={{ fontWeight: 500 }}>{title}</span>
      </div>
      <p className="t-body-sm text-dim" style={{ margin: 0 }}>{body}</p>
      <span className="t-code-sm text-muted">{foot}</span>
    </div>
  );
}

function ChallengeCard({ challenge, stat, index, starting, disabled, onStart }) {
  const attempts = stat?.attempts ?? 0;
  const solved = stat?.solved ?? 0;

  return (
    <motion.article
      className="card challenge-card"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.06, 0.3), duration: 0.35, ease: EASE }}
      whileHover={disabled ? undefined : { y: -1, borderColor: 'rgba(76, 141, 255, 0.4)', boxShadow: 'var(--elev-2)' }}
      {...{ transition: springTactile }}
    >
      <div className="card-body stack gap-md" style={{ height: '100%' }}>
        <div className="row gap-sm">
          <span className="t-code-sm text-dim">{challenge.repo_name}</span>
          <span className="spacer" />
          <span className={`chip ${challenge.difficulty === 'hard' ? 'chip-error' : challenge.difficulty === 'easy' ? 'chip-success' : 'chip-warning'}`}>
            {challenge.difficulty}
          </span>
        </div>

        <h2 className="t-title" style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--accent)', wordBreak: 'break-all' }}>
          {challenge.function_name}()
        </h2>

        <div className="row gap-sm wrap">
          <span className="chip">{challenge.language} </span>
          <span className="chip">{Math.round((challenge.time_limit_seconds || 300) / 60)} min</span>
          {/* Real count of hidden tests. The assertions themselves stay hidden. */}
          <span className="chip">{challenge.tests_total ?? NO_DATA} hidden tests</span>
        </div>

        {/* The first lines of the buggy function — never the ground-truth diff,
            which would hand over the answer before the timer starts. */}
        {challenge.code_preview && (
          <div className="preview">
            <div className="preview-head">
              <span className="t-code-sm text-muted">buggy source · preview</span>
            </div>
            <pre className="code preview-body">{challenge.code_preview}</pre>
          </div>
        )}

        <div className="row gap-md" style={{ marginTop: 'auto', paddingTop: 'var(--s-sm)' }}>
          <span className="t-code-sm text-muted">
            {attempts === 0
              ? 'No attempts yet'
              : `${attempts} ${attempts === 1 ? 'attempt' : 'attempts'} · ${solved} solved`}
          </span>
          <span className="spacer" />
          <button type="button" className="btn btn-primary btn-sm" onClick={onStart} disabled={disabled}>
            {starting ? 'Starting…' : 'Start challenge →'}
          </button>
        </div>
      </div>
    </motion.article>
  );
}
