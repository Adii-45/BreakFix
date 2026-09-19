import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { obsidianCodeMirror } from '../theme/codemirror.js';
import Countdown from '../components/Countdown.jsx';
import EvaluatingOverlay from '../components/EvaluatingOverlay.jsx';
import { SkeletonLine } from '../components/Skeleton.jsx';
import { api } from '../api.js';
import { useApp } from '../store.jsx';
import { EASE } from '../motion.js';

const SUBMIT_HINT = /Mac|iPhone|iPad/.test(typeof navigator === 'undefined' ? '' : navigator.userAgent)
  ? '⌘↵ to submit' : 'Ctrl+Enter to submit';

export default function Editor() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { refreshCatalogue, refreshLeaderboard } = useApp();

  /* The session arrives via router state from POST /sessions. A hard refresh
     loses it — the API has no GET /sessions/{id}, so we say so plainly rather
     than fabricating a session. */
  const session = location.state?.session ?? null;

  const [code, setCode] = useState(session?.buggy_code ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const autoSubmitted = useRef(false);

  const unchanged = session ? code.trim() === session.buggy_code.trim() : true;
  const empty = code.trim().length === 0;
  const blocked = submitting || empty || unchanged;

  const submit = useCallback(async (source) => {
    if (!session || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const result = await api.submitFix(session.session_id, source);
      refreshCatalogue();
      refreshLeaderboard();
      navigate(`/results/${session.session_id}`, { state: { result, session } });
    } catch (err) {
      if (err.status === 409 && err.payload?.result) {
        navigate(`/results/${session.session_id}`, { state: { result: err.payload.result, session } });
        return;
      }
      setError(err.message);
      setSubmitting(false);
    }
  }, [session, submitting, navigate, refreshCatalogue, refreshLeaderboard]);

  const handleExpire = useCallback(() => {
    if (autoSubmitted.current || submitting) return;
    autoSubmitted.current = true;
    submit(code);   // time is up — send whatever is in the editor
  }, [code, submit, submitting]);

  const extensions = useMemo(() => [python()], []);

  useEffect(() => {
    const onKey = (e) => {
      if (!((e.metaKey || e.ctrlKey) && e.key === 'Enter')) return;
      // CodeMirror binds Mod-Enter to "insert blank line". Claim the key in the
      // capture phase so the editor never sees it -- otherwise the shortcut we
      // advertise would append a stray line to the code being submitted.
      e.preventDefault();
      e.stopPropagation();
      if (!blocked) submit(code);
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [blocked, code, submit]);

  if (!session) {
    return (
      <div className="shell section-sm">
        <div className="card">
          <div className="empty-state">
            <span className="icon" aria-hidden="true">⟲</span>
            <span className="t-body" style={{ color: 'var(--text-dim)' }}>This session is no longer loaded.</span>
            <span className="t-body-sm text-muted">
              Sessions live in the page state for the duration of an attempt. Start a fresh one to continue.
            </span>
            <Link to="/challenges" className="btn btn-primary btn-sm" style={{ marginTop: 12 }}>
              Back to challenges
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="shell section-sm">
      {/* ------------------------------------------------------- breadcrumb */}
      <div className="row gap-md wrap" style={{ marginBottom: 'var(--s-lg)' }}>
        <Link to="/challenges" className="btn btn-ghost btn-sm">← Challenges</Link>
        <span className="t-code-sm text-muted">{session.repo_name}</span>
        <span className="t-code-sm text-muted">/</span>
        <span className="t-code-sm text-accent">{session.function_name}()</span>
        <span className={`chip ${session.difficulty === 'hard' ? 'chip-error' : 'chip-warning'}`}>{session.difficulty}</span>
        <span className="spacer" />
        <span className="chip">
          <span className="dot dot-live" style={{ color: 'var(--success)' }} />
          session {session.session_id.slice(0, 8)}
        </span>
      </div>

      {/* ----------------------------------------------------- mission brief */}
      <motion.div
        className="brief-grid"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: EASE }}
      >
        <div className="card objective">
          <div className="card-body stack gap-md">
            <div className="row gap-sm">
              <span className="t-label text-accent">Mission brief</span>
              <span className="spacer" />
              {session.source_url && (
                <a className="source-link" href={session.source_url} target="_blank" rel="noopener noreferrer">
                  view the real function on GitHub ↗
                </a>
              )}
            </div>

            {/* What this function does in the real codebase. */}
            {session.student_facing_summary ? (
              <p className="t-body-lg" style={{ margin: 0 }}>{session.student_facing_summary}</p>
            ) : (
              <p className="t-body-lg" style={{ margin: 0 }}>
                A real function from <span className="inline-code">{session.repo_name}</span>.
              </p>
            )}

            <p className="t-body text-dim" style={{ margin: 0 }}>
              A Bug Injector Agent introduced <strong>exactly one</strong> bug into it.
              {session.tests_total > 0
                ? ` ${session.tests_total} hidden unit tests will execute your submission in a sandbox — they decide pass or fail, and no model gets a vote on correctness.`
                : ' Hidden unit tests will execute your submission in a sandbox and decide pass or fail.'}
            </p>
          </div>
        </div>

        {/* The observable symptom — deliberately never the cause. */}
        <div className="card symptom-card">
          <div className="card-body stack gap-sm">
            <span className="t-label" style={{ color: 'var(--warning)' }}>Reported symptom</span>
            {session.symptom_description ? (
              <p className="t-body-lg" style={{ margin: 0 }}>{session.symptom_description}</p>
            ) : (
              <p className="t-body text-dim" style={{ margin: 0 }}>
                No symptom report was filed for this challenge.
              </p>
            )}
            <p className="t-body-sm text-muted" style={{ margin: '4px 0 0' }}>
              This describes what users observe. Locating the cause is the exercise.
            </p>
          </div>
        </div>
      </motion.div>

      {error && <div className="banner banner-error" style={{ marginTop: 'var(--s-lg)' }} role="alert">{error}</div>}

      {/* ----------------------------------------------------------- editor */}
      <div className="editor-layout" style={{ marginTop: 'var(--s-lg)' }}>
        <div className="code-panel">
          <div className="card-head">
            <div className="code-dots" aria-hidden="true">
              <i style={{ background: '#FF6B6B' }} /><i style={{ background: '#FFB84C' }} /><i style={{ background: '#3DD68C' }} />
            </div>
            <span className="t-code-sm" style={{ color: 'var(--accent)', marginLeft: 6 }}>{session.function_name}()</span>
            <span className="spacer" />
            <span className="chip">{session.language}</span>
            {!unchanged && <span className="chip chip-accent">modified</span>}
          </div>
          <CodeMirror
            value={code}
            onChange={setCode}
            extensions={extensions}
            theme={obsidianCodeMirror}
            height="clamp(360px, 60vh, 680px)"
            editable={!submitting}
            basicSetup={{
              lineNumbers: true,
              highlightActiveLine: true,
              highlightActiveLineGutter: true,
              bracketMatching: true,
              autocompletion: false,
              foldGutter: false,
            }}
          />
          <div className="row gap-md" style={{ padding: '9px 16px', borderTop: '1px solid var(--border)', background: 'rgba(255,255,255,.015)' }}>
            <span className="t-code-sm text-muted">
              {code.split('\n').length} lines
            </span>
            <span className="spacer" />
            <span className="t-code-sm text-muted">{SUBMIT_HINT}</span>
          </div>
        </div>

        {/* ------------------------------------------------------- side rail */}
        <div className="stack gap-lg editor-rail">
          <AnimatePresence mode="wait">
            {submitting ? (
              <EvaluatingOverlay key="evaluating" testsTotal={session.tests_total} />
            ) : (
              <motion.div key="live" className="stack gap-lg" exit={{ opacity: 0 }}>
                <Countdown
                  startTime={session.start_time}
                  limitSeconds={session.time_limit_seconds}
                  onExpire={handleExpire}
                />

                <section className="card">
                  <div className="card-head"><span className="t-label text-dim">This submission</span></div>
                  <div className="card-body stack gap-md">
                    <MetaRow k="Hidden tests" v={session.tests_total > 0 ? `${session.tests_total}` : '—'} />
                    <MetaRow k="Language" v={session.language} />
                    <MetaRow k="Source repo" v={session.repo_name} />
                    <MetaRow k="Status" v={unchanged ? 'unmodified' : 'edited'} tone={unchanged ? 'var(--text-muted)' : 'var(--accent)'} />
                  </div>
                </section>

                <div className="stack gap-sm">
                  <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => submit(code)} disabled={blocked}>
                    Submit fix for evaluation →
                  </button>
                  {unchanged && (
                    <span className="t-body-sm text-muted" style={{ textAlign: 'center' }}>
                      Edit the code before submitting.
                    </span>
                  )}
                </div>

                <div className="banner banner-note">
                  Your fix runs against hidden tests in a sandboxed Lambda with no network and a hard
                  timeout. An infinite loop is reported as a failing result, not an error.
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function MetaRow({ k, v, tone }) {
  return (
    <div className="row gap-md">
      <span className="t-body-sm text-dim">{k}</span>
      <span className="spacer" />
      <span className="t-code" style={{ color: tone || 'var(--text)' }}>{v}</span>
    </div>
  );
}
