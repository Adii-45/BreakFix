import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { EASE } from '../motion.js';

/**
 * Submit can take several seconds: a sandboxed Lambda test run followed by a
 * Bedrock call. The API returns once, at the end, so there is no real progress
 * stream to subscribe to.
 *
 * These stages are therefore a *description of the real pipeline* on an
 * estimated timeline, not measured progress — the last stage deliberately holds
 * until the response lands rather than claiming completion the backend has not
 * confirmed. Nothing here reports a number the server did not send.
 */
const STAGES = [
  { label: 'Sending your diff to the API', detail: 'API Gateway → submit Lambda' },
  { label: 'Running hidden tests in the sandbox', detail: 'Isolated Lambda · no network, no filesystem' },
  { label: 'Evaluating your approach', detail: 'Amazon Bedrock · Evaluator Agent' },
];
const ADVANCE_MS = [900, 2600];

export default function EvaluatingOverlay({ testsTotal }) {
  const reduced = useReducedMotion();
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const timers = ADVANCE_MS.map((ms, i) => setTimeout(() => setStage(i + 1), ms));
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <motion.div
      className="card eval-overlay"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EASE }}
      role="status"
      aria-live="polite"
    >
      <div className="card-body stack gap-lg">
        <div className="row gap-md">
          <span className="t-label text-accent">Evaluating submission</span>
          <span className="spacer" />
          {testsTotal > 0 && <span className="chip">{testsTotal} hidden tests</span>}
        </div>

        <div className="stack gap-md">
          {STAGES.map((item, i) => {
            const done = i < stage;
            const active = i === stage;
            return (
              <div key={item.label} className="row gap-md" style={{ alignItems: 'flex-start', opacity: i > stage ? 0.4 : 1 }}>
                <span className="eval-pip" data-state={done ? 'done' : active ? 'active' : 'idle'}>
                  {done ? '✓' : active && !reduced ? <span className="eval-spin" /> : ''}
                </span>
                <div className="stack" style={{ gap: 1 }}>
                  <span className="t-body" style={{ color: done || active ? 'var(--text)' : 'var(--text-muted)' }}>
                    {item.label}
                  </span>
                  <span className="t-code-sm text-muted">{item.detail}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Indeterminate — deliberately not a percentage, since the backend
            reports no progress to base one on. */}
        <div className="eval-track" aria-hidden="true">
          <motion.div
            className="eval-bar"
            animate={reduced ? {} : { x: ['-40%', '140%'] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
          />
        </div>

        <p className="t-body-sm text-muted" style={{ margin: 0 }}>
          The verdict comes from the test run, not from the model. If Bedrock is unreachable the score
          still arrives — labelled as a fallback.
        </p>
      </div>
    </motion.div>
  );
}
