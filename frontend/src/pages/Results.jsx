import { Link, useLocation, useParams } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import ScoreRing from '../components/ScoreRing.jsx';
import { LeaderboardEmpty, LeaderboardList } from '../components/LeaderboardRows.jsx';
import { useApp } from '../store.jsx';
import { formatDuration } from '../api.js';
import { EASE, springTactile } from '../motion.js';

export default function Results() {
  const { sessionId } = useParams();
  const location = useLocation();
  const reduced = useReducedMotion();
  const { leaderboard, displayName } = useApp();

  /* The entire screen renders from the POST /sessions/{id}/submit response that
     was handed over in router state. Nothing below is synthesised. */
  const result = location.state?.result ?? null;
  const session = location.state?.session ?? null;

  if (!result) {
    return (
      <div className="shell section-sm">
        <div className="card">
          <div className="empty-state">
            <span className="icon" aria-hidden="true">⟲</span>
            <span className="t-body" style={{ color: 'var(--text-dim)' }}>No result is loaded for this session.</span>
            <span className="t-body-sm text-muted">
              Results are returned once, by the submit call. Take a challenge to generate a new one.
            </span>
            <Link to="/challenges" className="btn btn-primary btn-sm" style={{ marginTop: 12 }}>Back to challenges</Link>
          </div>
        </div>
      </div>
    );
  }

  const passed = Boolean(result.correct);
  const fallback = result.feedback_source === 'fallback-heuristic';
  const label = session ? `${session.repo_name} · ${session.function_name}()` : sessionId;

  return (
    <div className="shell section-sm">
      <div className="row gap-md wrap" style={{ marginBottom: 'var(--s-lg)' }}>
        <span className="t-code-sm text-muted">Submission</span>
        <span className="t-code-sm text-accent">{label}</span>
        <span className="spacer" />
        <span className={`chip ${passed ? 'chip-success' : 'chip-error'}`}>
          {passed ? 'verified solved' : 'not solved'}
        </span>
      </div>

      {/* ------------------------------------------------------- verdict card */}
      <motion.div
        className={`card verdict ${passed ? 'verdict-pass' : 'verdict-fail'}`}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: EASE }}
      >
        <div className="card-body verdict-body">
          <div className="stack gap-lg" style={{ flex: 1, minWidth: 260 }}>
            <motion.div
              className="row gap-md"
              initial={reduced ? false : { opacity: 0, scale: 0.86 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ type: 'spring', stiffness: 260, damping: 18, delay: 0.1 }}
            >
              <span className={`verdict-glyph ${passed ? 'is-pass' : 'is-fail'}`} aria-hidden="true">
                {passed ? '✓' : '✕'}
              </span>
              <div className="stack" style={{ gap: 2 }}>
                <h1 className="t-title" style={{ margin: 0 }}>
                  {passed ? 'All hidden tests pass' : 'Hidden tests still failing'}
                </h1>
                <span className="t-body-sm text-dim">
                  {result.tests_passed} of {result.tests_total} tests passed · {formatDuration(result.time_taken_seconds)} taken
                </span>
              </div>
            </motion.div>

            <div className="verdict-stats">
              <Stat k="Verdict" v={passed ? 'PASS' : 'FAIL'} tone={passed ? 'var(--success)' : 'var(--error)'} />
              <Stat k="Hidden tests" v={`${result.tests_passed}/${result.tests_total}`} />
              <Stat k="Quality score" v={result.score} />
              <Stat k="Time taken" v={formatDuration(result.time_taken_seconds)} />
            </div>
          </div>

          <ScoreRing score={result.score} passed={passed} />
        </div>
      </motion.div>

      {result.execution_error && (
        <div className="banner banner-error" style={{ marginTop: 'var(--s-lg)' }} role="alert">
          <span><strong>Sandbox:</strong> {result.execution_error}</span>
        </div>
      )}

      {/* ---------------------------------------------------------- detail */}
      <div className="results-grid" style={{ marginTop: 'var(--s-lg)' }}>
        {/* Correctness — straight from the Test Runner */}
        <motion.section
          className="card"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: EASE, delay: 0.1 }}
        >
          <div className="card-head">
            <span className="t-label text-dim">Correctness · test execution</span>
            <span className="spacer" />
            <span className={`chip ${passed ? 'chip-success' : 'chip-error'}`}>
              {result.tests_passed}/{result.tests_total} passed
            </span>
          </div>
          <div className="card-body stack gap-sm">
            {(result.test_summary || []).map((test, index) => (
              <motion.div
                key={index}
                className="test-row"
                initial={reduced ? false : { opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 + index * 0.06, duration: 0.28, ease: EASE }}
              >
                <span className={`test-dot ${test.passed ? 'is-pass' : 'is-fail'}`} aria-hidden="true" />
                <span className="t-body" style={{ color: test.passed ? 'var(--text)' : 'var(--text-dim)' }}>
                  {test.name}
                </span>
                <span className="spacer" />
                <span className={`t-code-sm ${test.passed ? 'text-ok' : 'text-err'}`}>
                  {test.passed ? 'pass' : 'fail'}
                </span>
              </motion.div>
            ))}
            {(!result.test_summary || result.test_summary.length === 0) && (
              <span className="t-body-sm text-muted">No per-test detail was returned for this submission.</span>
            )}
            <div className="banner banner-note" style={{ marginTop: 6 }}>
              Executed in an isolated Lambda with no network access and a hard timeout. This result — not
              the agent below — is what decides pass or fail.
            </div>
          </div>
        </motion.section>

        {/* Quality — straight from the Evaluator Agent */}
        <motion.section
          className="card"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: EASE, delay: 0.16 }}
        >
          <div className="card-head">
            <span className="t-label text-dim">How you debugged · Evaluator Agent</span>
            <span className="spacer" />
            <span className={`chip ${fallback ? 'chip-warning' : 'chip-accent'}`}>
              {fallback ? 'offline fallback' : 'amazon bedrock'}
            </span>
          </div>
          <div className="card-body stack gap-lg">
            {fallback && (
              <div className="banner banner-note">
                Bedrock was unreachable, so this feedback came from the deterministic fallback scorer.
                The pass/fail verdict is unaffected — it comes from the test run.
              </div>
            )}

            {/* The real process_feedback string for THIS submission. */}
            <blockquote className="quote">
              {result.process_feedback}
            </blockquote>

            <div className="stack gap-xs">
              <span className="t-label text-dim">Why the tests landed that way</span>
              <p className="t-body" style={{ margin: 0 }}>{result.correctness_notes}</p>
            </div>

            <div className="stack gap-xs">
              <span className="t-label text-dim">Scoring rubric applied</span>
              <p className="t-body-sm text-muted" style={{ margin: 0 }}>
                100 = tests pass with a minimal, targeted fix · 60–80 = tests pass but the fix is broader
                than necessary · 20–50 = tests fail but the approach was on the right track · 0 = tests
                fail and the bug was missed. The agent is given the test outcome and cannot contradict it.
              </p>
            </div>
          </div>
        </motion.section>
      </div>

      {/* ------------------------------------------------------ leaderboard */}
      <div className="results-grid" style={{ marginTop: 'var(--s-lg)' }}>
        <motion.section
          className="card"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: EASE, delay: 0.22 }}
        >
          <div className="card-head"><span className="t-label text-dim">Leaderboard</span></div>
          <div className="card-body">
            {leaderboard === null || leaderboard.length === 0
              ? <LeaderboardEmpty />
              : <LeaderboardList entries={leaderboard.slice(0, 5)} highlightName={displayName} />}
          </div>
        </motion.section>

        <motion.div
          className="card next-card"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: EASE, delay: 0.26 }}
        >
          <div className="card-body stack gap-md" style={{ height: '100%' }}>
            <span className="t-label text-accent">What next</span>
            <h2 className="t-subtitle" style={{ margin: 0 }}>
              {passed ? 'Try a harder function' : 'Take another run at it'}
            </h2>
            <p className="t-body text-dim" style={{ margin: 0 }}>
              {passed
                ? 'Each challenge uses a different bug category — off-by-one, wrong condition, swapped variable, incorrect boundary.'
                : 'Each attempt starts a fresh session, so the clock and the scoring both reset.'}
            </p>
            <div className="row gap-sm wrap" style={{ marginTop: 'auto' }}>
              <motion.div whileHover={{ y: -1 }} whileTap={{ y: 0 }} transition={springTactile}>
                <Link to="/challenges" className="btn btn-primary">Try another challenge →</Link>
              </motion.div>
              <Link to="/leaderboard" className="btn btn-secondary">View leaderboard</Link>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}

function Stat({ k, v, tone }) {
  return (
    <div className="stack" style={{ gap: 3 }}>
      <span className="t-label text-dim">{k}</span>
      <span className="num" style={{ font: '500 20px/1.2 var(--font-mono)', color: tone || 'var(--text)' }}>{v}</span>
    </div>
  );
}
