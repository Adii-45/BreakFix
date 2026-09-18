import { useCallback, useMemo, useRef, useState } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { githubDark } from '@uiw/codemirror-theme-github';
import Timer from './Timer.jsx';

export default function EditorScreen({ session, onSubmit, submitting, error, onAbandon }) {
  const [code, setCode] = useState(session.buggy_code);
  const startedAt = useRef(Date.now()).current;
  const autoSubmitted = useRef(false);

  const unchanged = code.trim() === session.buggy_code.trim();
  const empty = code.trim().length === 0;
  // PRD 12.1: the submit button is disabled on empty or unchanged submissions,
  // so a no-op never reaches the API.
  const blocked = submitting || empty || unchanged;

  const handleSubmit = useCallback(() => {
    if (!blocked) onSubmit(code);
  }, [blocked, code, onSubmit]);

  const handleExpire = useCallback(() => {
    if (autoSubmitted.current || submitting) return;
    autoSubmitted.current = true;
    // Time is up: send whatever is in the editor. The server scores the real
    // elapsed time either way, so there is nothing to gain by stalling.
    onSubmit(code);
  }, [code, onSubmit, submitting]);

  const extensions = useMemo(() => [python()], []);

  return (
    <>
      {error && <div className="banner" role="alert">{error}</div>}
      <div className="editor-grid">
        <div className="editor-shell">
          <div className="editor-bar">
            <span className="fn">{session.function_name}()</span>
            <span className="path">{session.repo_name}</span>
            <span style={{ flex: 1 }} />
            <span className="pill">{session.language}</span>
          </div>
          <div className="cm-theme-wrap">
            <CodeMirror
              value={code}
              onChange={setCode}
              theme={githubDark}
              extensions={extensions}
              height="clamp(340px, 58vh, 640px)"
              basicSetup={{ lineNumbers: true, highlightActiveLine: true, bracketMatching: true, autocompletion: false }}
              aria-label={`Source of ${session.function_name}, editable`}
            />
          </div>
        </div>

        <div className="side-stack">
          <Timer startedAt={startedAt} limitSeconds={session.time_limit_seconds} onExpire={handleExpire} />

          <section className="panel">
            <div className="panel-head"><h2>Brief</h2></div>
            <div className="panel-body hint-box">
              <p style={{ marginTop: 0 }}>
                An AI agent injected <strong>exactly one</strong> bug into this real function from{' '}
                <strong>{session.repo_name}</strong>.
              </p>
              <p style={{ marginBottom: 0 }}>
                Your fix is checked by <strong>hidden unit tests</strong> that actually run your code — not by an
                AI reading it. A second agent then reviews <em>how</em> you fixed it.
              </p>
            </div>
          </section>

          <button type="button" className="btn btn-primary btn-lg" onClick={handleSubmit} disabled={blocked}>
            {submitting ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9 }}>
                <span className="spinner" /> Running hidden tests…
              </span>
            ) : (
              'Submit fix'
            )}
          </button>
          {unchanged && !submitting && (
            <p className="empty" style={{ margin: 0 }}>Edit the code before submitting.</p>
          )}
          <button type="button" className="btn btn-ghost" onClick={onAbandon} disabled={submitting}>
            Back to challenges
          </button>
        </div>
      </div>
    </>
  );
}
