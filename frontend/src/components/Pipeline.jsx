import { motion, useReducedMotion } from 'motion/react';
import { EASE, viewportOnce } from '../motion.js';

/**
 * The real end-to-end pipeline (PRD 5.1 / 5.3). Node copy describes what the
 * code in this repo actually does — no invented stages, no fabricated latency
 * figures. Connecting lines draw themselves on scroll-into-view via SVG
 * pathLength, which is why this needs no GSAP.
 */
const NODES = [
  {
    n: '01',
    title: 'Real OSS function',
    agent: 'Offline · GitHub-sourced',
    body: 'A pure function is lifted from a permissively-licensed repository and trimmed of repo-internal imports so it runs standalone.',
    meta: 'python/cpython · django · humanize · werkzeug',
    tone: 'var(--text-dim)',
  },
  {
    n: '02',
    title: 'Bug Injector Agent',
    agent: 'Amazon Bedrock · offline',
    body: 'Given the clean function and a bug category, the agent returns one realistic, non-trivial bug plus a structured ground-truth explanation.',
    meta: 'Discarded unless it breaks a hidden test',
    tone: 'var(--accent)',
  },
  {
    n: '03',
    title: 'You fix it',
    agent: 'Human in the loop',
    body: 'The buggy function loads into the editor against a countdown. Elapsed time is measured server-side from the session start.',
    meta: 'CodeMirror 6 · session-authoritative clock',
    tone: 'var(--text-dim)',
  },
  {
    n: '04',
    title: 'Test Runner',
    agent: 'AWS Lambda · sandboxed',
    body: 'Your submission executes against the hidden tests in an isolated process with no network, no filesystem and a hard timeout. This decides correctness.',
    meta: 'Zero IAM permissions on this function',
    tone: 'var(--success)',
  },
  {
    n: '05',
    title: 'Evaluator Agent',
    agent: 'Amazon Bedrock · live',
    body: 'Handed the test outcome as fact, the agent scores fix quality and explains your debugging process. It can never change the verdict.',
    meta: 'Score clamped to the band the verdict allows',
    tone: 'var(--accent)',
  },
];

export default function Pipeline() {
  const reduced = useReducedMotion();

  return (
    <div className="pipeline">
      {/* Connector rail — draws left to right as the section enters view. */}
      <svg className="pipeline-rail" viewBox="0 0 1000 2" preserveAspectRatio="none" aria-hidden="true">
        <line x1="0" y1="1" x2="1000" y2="1" stroke="var(--border)" strokeWidth="2" />
        <motion.line
          x1="0" y1="1" x2="1000" y2="1"
          stroke="var(--accent)" strokeWidth="2" strokeLinecap="round"
          initial={reduced ? { pathLength: 1 } : { pathLength: 0 }}
          whileInView={{ pathLength: 1 }}
          viewport={viewportOnce}
          transition={reduced ? { duration: 0 } : { duration: 1.6, ease: EASE, delay: 0.2 }}
          style={{ filter: 'drop-shadow(0 0 6px rgba(255, 153, 0,.5))' }}
        />
      </svg>

      <div className="pipeline-nodes">
        {NODES.map((node, i) => (
          <motion.div
            key={node.n}
            className="card pipeline-node"
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={viewportOnce}
            transition={{ duration: 0.4, ease: EASE, delay: reduced ? 0 : 0.25 + i * 0.12 }}
          >
            <motion.span
              className="pipeline-pip"
              style={{ background: node.tone }}
              initial={reduced ? { scale: 1 } : { scale: 0 }}
              whileInView={{ scale: 1 }}
              viewport={viewportOnce}
              transition={{ type: 'spring', stiffness: 380, damping: 20, delay: reduced ? 0 : 0.3 + i * 0.12 }}
            />
            <div className="card-body stack gap-sm">
              <div className="row gap-sm">
                <span className="t-label" style={{ color: node.tone }}>node {node.n}</span>
                <span className="spacer" />
              </div>
              <h3 className="t-subtitle" style={{ margin: 0 }}>{node.title}</h3>
              <span className="t-code-sm text-muted">{node.agent}</span>
              <p className="t-body text-dim" style={{ margin: '2px 0 0' }}>{node.body}</p>
              <span className="chip" style={{ marginTop: 6, alignSelf: 'flex-start', whiteSpace: 'normal', textTransform: 'none', letterSpacing: 0 }}>
                {node.meta}
              </span>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
