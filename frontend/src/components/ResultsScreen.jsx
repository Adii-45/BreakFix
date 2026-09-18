import { formatDuration } from '../api.js';

export default function ResultsScreen({ result, challengeLabel, onRestart }) {
  const passed = result.correct;
  const fallback = result.feedback_source === 'fallback-heuristic';

  return (
    <>
      <div className={`verdict ${passed ? 'pass' : 'fail'}`}>
        <div>
          <span className="score">{result.score}</span>
          <span className="score-unit"> / 100</span>
        </div>
        <div>
          <h2>{passed ? 'Fixed — all hidden tests pass' : 'Not fixed yet'}</h2>
          <p>
            {challengeLabel} · {result.tests_passed} of {result.tests_total} hidden tests passed ·{' '}
            {formatDuration(result.time_taken_seconds)} taken
          </p>
        </div>
      </div>

      <div className="stat-row">
        <div className="stat">
          <div className="k">Verdict</div>
          <div className="v" style={{ color: passed ? 'var(--pass)' : 'var(--fail)' }}>
            {passed ? 'PASS' : 'FAIL'}
          </div>
        </div>
        <div className="stat">
          <div className="k">Hidden tests</div>
          <div className="v">{result.tests_passed}/{result.tests_total}</div>
        </div>
        <div className="stat">
          <div className="k">Quality score</div>
          <div className="v">{result.score}</div>
        </div>
        <div className="stat">
          <div className="k">Time taken</div>
          <div className="v">{formatDuration(result.time_taken_seconds)}</div>
        </div>
      </div>

      {result.execution_error && (
        <div className="banner" role="alert">
          <span>Sandbox: {result.execution_error}</span>
        </div>
      )}

      <div className="layout-split">
        <section className="panel">
          <div className="panel-head">
            <h2>Evaluator Agent</h2>
            <span style={{ flex: 1 }} />
            <span className="pill">{fallback ? 'offline fallback' : 'Amazon Bedrock'}</span>
          </div>
          <div className="panel-body">
            {fallback && (
              <div className="banner note">
                Bedrock was unreachable, so this feedback came from the deterministic fallback. The pass/fail
                verdict above is unaffected — it comes from real test execution.
              </div>
            )}
            <div className="feedback-block">
              <span className="who">Debugging process</span>
              <p>{result.process_feedback}</p>
            </div>
            <div className="feedback-block">
              <span className="who">Why the tests landed that way</span>
              <p>{result.correctness_notes}</p>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><h2>Hidden tests</h2></div>
          <div className="panel-body">
            <ul className="test-list">
              {(result.test_summary || []).map((test, index) => (
                <li key={index}>
                  <span className={`dot ${test.passed ? 'p' : 'f'}`} />
                  <span>{test.name}</span>
                </li>
              ))}
            </ul>
            {(!result.test_summary || result.test_summary.length === 0) && (
              <p className="empty">No per-test detail available.</p>
            )}
          </div>
        </section>
      </div>

      <div style={{ display: 'flex', gap: 10, marginTop: 22, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-primary btn-lg" onClick={onRestart}>
          Try another challenge
        </button>
      </div>
    </>
  );
}
