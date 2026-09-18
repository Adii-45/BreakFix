import { useCallback, useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { api } from '../api.js';
import { useApp } from '../store.jsx';
import { LiveDot } from '../components/ActivityFeed.jsx';
import { EASE, springTactile } from '../motion.js';

const PASS_KEY = 'breakfix.adminPass';

/* A worked example the demo can paste in. It is a real cpython function that
   genuinely extracts standalone — most library functions do not, because they
   import from their own package, and the pipeline rejects those on purpose. */
const SAMPLE = {
  github_url: 'https://github.com/python/cpython/blob/main/Lib/shlex.py',
  function_name: 'quote',
  test_cases: JSON.stringify([
    { name: 'a safe token is untouched', input: ['abc'], expected_output: 'abc' },
    { name: 'spaces force quoting', input: ['a b'], expected_output: "'a b'" },
    { name: 'the empty string becomes quotes', input: [''], expected_output: "''" },
  ], null, 2),
};

export default function Admin() {
  const { authoring } = useApp();
  const [passphrase, setPassphrase] = useState(() => {
    try { return sessionStorage.getItem(PASS_KEY) || ''; } catch { return ''; }
  });
  const [unlocked, setUnlocked] = useState(false);
  const [authError, setAuthError] = useState('');
  const [pending, setPending] = useState([]);
  const [execution, setExecution] = useState(null);
  const [form, setForm] = useState({
    github_url: '', function_name: '', test_cases: '',
    student_facing_summary: '', symptom_description: '',
    difficulty: 'medium', time_limit_seconds: 300,
  });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const loadPending = useCallback(async (pass) => {
    const data = await api.admin.listPending(pass || passphrase);
    setPending(data.pending || []);
  }, [passphrase]);

  const unlock = useCallback(async (event) => {
    event?.preventDefault();
    setAuthError('');
    try {
      await loadPending(passphrase);
      setUnlocked(true);
      try { sessionStorage.setItem(PASS_KEY, passphrase); } catch { /* private mode */ }
    } catch (err) {
      setUnlocked(false);
      setAuthError(err.message);
    }
  }, [loadPending, passphrase]);

  useEffect(() => { if (passphrase && !unlocked) unlock(); /* eslint-disable-next-line */ }, []);

  /* Step transitions arrive over the same WebSocket as the rest of the live
     layer; this poll is only a safety net for the deployed Step Functions path,
     where progress is read with DescribeExecution. */
  useEffect(() => {
    if (authoring) setExecution(authoring);
  }, [authoring]);

  useEffect(() => {
    if (!execution || execution.status !== 'RUNNING' || !unlocked) return undefined;
    const id = setInterval(async () => {
      try {
        const data = await api.admin.getExecution(passphrase, execution.execution_id);
        setExecution(data.execution);
        if (data.execution.status !== 'RUNNING') loadPending();
      } catch { /* the socket is the primary channel */ }
    }, 1500);
    return () => clearInterval(id);
  }, [execution, passphrase, unlocked, loadPending]);

  const start = useCallback(async (event) => {
    event.preventDefault();
    setBusy(true); setNotice('');
    try {
      const payload = { ...form, time_limit_seconds: Number(form.time_limit_seconds) || 300 };
      if (payload.test_cases?.trim()) {
        try { payload.test_cases = JSON.parse(payload.test_cases); }
        catch { setNotice('test_cases must be valid JSON.'); setBusy(false); return; }
      } else {
        delete payload.test_cases;
      }
      const data = await api.admin.startAuthoring(passphrase, payload);
      setExecution(data.execution);
    } catch (err) {
      setNotice(err.message);
    } finally {
      setBusy(false);
    }
  }, [form, passphrase]);

  const publish = useCallback(async (challenge) => {
    setBusy(true); setNotice('');
    try {
      await api.admin.publish(passphrase, challenge.challenge_id, {
        student_facing_summary: challenge.student_facing_summary,
        symptom_description: challenge.symptom_description,
      });
      setNotice(`${challenge.challenge_id} published — it is now visible to everyone.`);
      await loadPending();
    } catch (err) {
      setNotice(err.message);
    } finally {
      setBusy(false);
    }
  }, [passphrase, loadPending]);

  const reject = useCallback(async (challenge) => {
    setBusy(true);
    try {
      await api.admin.reject(passphrase, challenge.challenge_id);
      await loadPending();
    } finally { setBusy(false); }
  }, [passphrase, loadPending]);

  if (!unlocked) {
    return (
      <div className="shell section-sm" style={{ maxWidth: 460 }}>
        <div className="card">
          <div className="card-head"><span className="t-label text-dim">Restricted</span></div>
          <form className="card-body stack gap-lg" onSubmit={unlock}>
            <div className="stack gap-sm">
              <h1 className="t-title" style={{ margin: 0 }}>Challenge authoring</h1>
              <p className="t-body text-dim" style={{ margin: 0 }}>
                Runs the live pipeline and gates what reaches students. Admin passphrase required.
              </p>
            </div>
            <div>
              <label className="field-label" htmlFor="pass">Admin passphrase</label>
              <input
                id="pass" className="input" type="password" autoComplete="current-password"
                value={passphrase} onChange={(e) => setPassphrase(e.target.value)}
              />
            </div>
            {authError && <div className="banner banner-error" role="alert">{authError}</div>}
            <button type="submit" className="btn btn-primary btn-block">Unlock</button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="shell section-sm">
      <div className="row gap-md wrap" style={{ marginBottom: 'var(--s-xl)' }}>
        <div className="stack gap-sm" style={{ flex: 1, minWidth: 280 }}>
          <span className="eyebrow">Admin · gated authoring</span>
          <h1 className="t-headline" style={{ margin: 0 }}>Author a challenge live</h1>
          <p className="t-body-lg text-dim measure" style={{ margin: 0 }}>
            The pipeline runs every gate the seeded challenges passed. It ends at{' '}
            <span className="inline-code">pending_review</span> — nothing reaches students without the
            approval below.
          </p>
        </div>
        <LiveDot connected label="step updates pushed live" />
      </div>

      {notice && <div className="banner banner-note" style={{ marginBottom: 'var(--s-lg)' }}>{notice}</div>}

      <div className="admin-grid">
        {/* ------------------------------------------------------------ form */}
        <form className="card" onSubmit={start}>
          <div className="card-head">
            <span className="t-label text-dim">New challenge</span>
            <span className="spacer" />
            <button type="button" className="btn btn-ghost btn-sm"
              onClick={() => setForm((f) => ({ ...f, ...SAMPLE }))}>
              use worked example
            </button>
          </div>
          <div className="card-body stack gap-lg">
            <div>
              <label className="field-label" htmlFor="url">GitHub file URL</label>
              <input id="url" className="input input-mono" placeholder="https://github.com/owner/repo/blob/main/path.py"
                value={form.github_url} onChange={(e) => setForm({ ...form, github_url: e.target.value })} />
            </div>
            <div className="row gap-md">
              <div style={{ flex: 1 }}>
                <label className="field-label" htmlFor="fn">Function name</label>
                <input id="fn" className="input input-mono" placeholder="quote"
                  value={form.function_name} onChange={(e) => setForm({ ...form, function_name: e.target.value })} />
              </div>
              <div style={{ width: 120 }}>
                <label className="field-label" htmlFor="diff">Difficulty</label>
                <select id="diff" className="input" value={form.difficulty}
                  onChange={(e) => setForm({ ...form, difficulty: e.target.value })}>
                  <option value="easy">easy</option>
                  <option value="medium">medium</option>
                  <option value="hard">hard</option>
                </select>
              </div>
            </div>
            <div>
              <label className="field-label" htmlFor="tests">Hidden test cases (JSON)</label>
              <textarea id="tests" className="input input-mono" rows={7}
                placeholder='[{"name":"...","input":[...],"expected_output":...}]'
                value={form.test_cases} onChange={(e) => setForm({ ...form, test_cases: e.target.value })} />
              <span className="t-body-sm text-muted">
                Leave empty to have the Test Author Agent propose them. Either way they are run against the
                clean function first, and the run stops if any fail.
              </span>
            </div>
            <div>
              <label className="field-label" htmlFor="purpose">Mission brief — purpose</label>
              <textarea id="purpose" className="input" rows={2}
                value={form.student_facing_summary}
                onChange={(e) => setForm({ ...form, student_facing_summary: e.target.value })} />
            </div>
            <div>
              <label className="field-label" htmlFor="symptom">Mission brief — observable symptom</label>
              <textarea id="symptom" className="input" rows={2}
                value={form.symptom_description}
                onChange={(e) => setForm({ ...form, symptom_description: e.target.value })} />
              <span className="t-body-sm text-muted">
                Leave empty for the Mission Brief Agent. Whoever writes it, it is leak-checked before publish.
              </span>
            </div>
            <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
              {busy ? 'Starting…' : 'Run the authoring pipeline →'}
            </button>
          </div>
        </form>

        {/* ------------------------------------------------------- execution */}
        <div className="stack gap-lg">
          <ExecutionPanel execution={execution} />

          <section className="card">
            <div className="card-head">
              <span className="t-label text-dim">Awaiting review</span>
              <span className="spacer" />
              <span className="chip">{pending.length}</span>
            </div>
            <div className="card-body stack gap-lg">
              {pending.length === 0 ? (
                <div className="empty-state" style={{ padding: 'var(--s-lg) 0' }}>
                  <span className="t-body" style={{ color: 'var(--text-dim)' }}>Nothing awaiting review.</span>
                  <span className="t-body-sm text-muted">Successful runs land here for approval.</span>
                </div>
              ) : pending.map((challenge) => (
                <PendingCard key={challenge.challenge_id} challenge={challenge}
                  busy={busy} onPublish={publish} onReject={reject} />
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function ExecutionPanel({ execution }) {
  const tone = { SUCCEEDED: 'chip-success', FAILED: 'chip-error', RUNNING: 'chip-accent' };
  return (
    <section className="card">
      <div className="card-head">
        <span className="t-label text-dim">Pipeline execution</span>
        <span className="spacer" />
        {execution && <span className={`chip ${tone[execution.status] || ''}`}>{execution.status}</span>}
      </div>
      <div className="card-body">
        {!execution ? (
          <div className="empty-state" style={{ padding: 'var(--s-lg) 0' }}>
            <span className="t-body" style={{ color: 'var(--text-dim)' }}>No run yet.</span>
            <span className="t-body-sm text-muted">Start one to watch each gate resolve in real time.</span>
          </div>
        ) : (
          <div className="stack gap-sm">
            <span className="t-code-sm text-muted" style={{ wordBreak: 'break-all' }}>
              {execution.execution_id}
            </span>
            {execution.steps.map((step, index) => (
              <motion.div key={step.name} className="step-row" layout
                initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25, ease: EASE, delay: index * 0.02 }}>
                <StepPip status={step.status} />
                <div className="stack" style={{ gap: 1, minWidth: 0 }}>
                  <span className="t-body" style={{
                    color: step.status === 'PENDING' ? 'var(--text-muted)' : 'var(--text)' }}>
                    {step.label}
                  </span>
                  {step.detail && (
                    <span className={`t-code-sm ${step.status === 'FAILED' ? 'text-err' : 'text-muted'}`}>
                      {step.detail}
                    </span>
                  )}
                </div>
              </motion.div>
            ))}
            <AnimatePresence>
              {execution.status === 'FAILED' && execution.error && (
                <motion.div className="banner banner-error" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <span><strong>Gate rejected the run.</strong> {execution.error}</span>
                </motion.div>
              )}
              {execution.status === 'SUCCEEDED' && (
                <motion.div className="banner banner-accent" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  Landed as <span className="inline-code">{execution.challenge_id}</span> in pending_review.
                  Still invisible to students until approved.
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </section>
  );
}

function StepPip({ status }) {
  const map = {
    SUCCEEDED: { bg: 'rgba(61,214,140,.15)', bd: 'rgba(61,214,140,.45)', fg: 'var(--success)', glyph: '✓' },
    FAILED: { bg: 'rgba(255,107,107,.15)', bd: 'rgba(255,107,107,.45)', fg: 'var(--error)', glyph: '✕' },
    RUNNING: { bg: 'transparent', bd: 'var(--accent)', fg: 'var(--accent)', glyph: '' },
    PENDING: { bg: 'var(--canvas)', bd: 'var(--border)', fg: 'var(--text-muted)', glyph: '' },
  };
  const s = map[status] || map.PENDING;
  return (
    <span className="step-pip" style={{ background: s.bg, borderColor: s.bd, color: s.fg }}>
      {s.glyph || (status === 'RUNNING' ? <span className="eval-spin" /> : '')}
    </span>
  );
}

function PendingCard({ challenge, busy, onPublish, onReject }) {
  const [summary, setSummary] = useState(challenge.student_facing_summary || '');
  const [symptom, setSymptom] = useState(challenge.symptom_description || '');
  const ready = summary.trim().length >= 40 && symptom.trim().length >= 20;
  const groundTruth = useMemo(() => {
    try { return JSON.parse(challenge.ground_truth_diff || '{}'); } catch { return {}; }
  }, [challenge.ground_truth_diff]);

  return (
    <div className="card pending-card">
      <div className="card-body stack gap-md">
        <div className="row gap-sm wrap">
          <span className="t-code" style={{ color: 'var(--accent)' }}>{challenge.function_name}()</span>
          <span className="spacer" />
          <span className="chip">{challenge.tests_total} tests</span>
          <span className="chip">{challenge.bug_category}</span>
        </div>
        <span className="t-code-sm text-muted">{challenge.repo_name} · {challenge.challenge_id}</span>

        <div className="row gap-sm wrap">
          <span className="chip">bug: {challenge.injection_source}</span>
          <span className="chip">tests: {challenge.tests_source}</span>
          <span className="chip">brief: {challenge.brief_source}</span>
        </div>

        {groundTruth.diff_summary && (
          <div className="banner banner-note">
            <span><strong>Ground truth (admin only):</strong> {groundTruth.diff_summary}</span>
          </div>
        )}

        <div>
          <label className="field-label">Purpose (shown to students)</label>
          <textarea className="input" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </div>
        <div>
          <label className="field-label">Observable symptom</label>
          <textarea className="input" rows={2} value={symptom} onChange={(e) => setSymptom(e.target.value)} />
        </div>

        <div className="row gap-sm wrap">
          <motion.button type="button" className="btn btn-primary btn-sm"
            disabled={busy || !ready} whileHover={{ y: -1 }} transition={springTactile}
            onClick={() => onPublish({ ...challenge, student_facing_summary: summary, symptom_description: symptom })}>
            Approve &amp; publish
          </motion.button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
            onClick={() => onReject(challenge)}>
            Reject
          </button>
          {!ready && <span className="t-body-sm text-muted">A mission brief is required before publishing.</span>}
        </div>
      </div>
    </div>
  );
}
