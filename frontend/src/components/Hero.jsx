import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { EASE } from '../motion.js';

const LINE_1 = 'Find the bug. Fix it.';
const LINE_2 = 'Get judged on how.';

/** Word-by-word reveal, then a highlight sweep across the accent phrase. */
export function HeroHeadline() {
  const reduced = useReducedMotion();
  const words1 = LINE_1.split(' ');
  const words2 = LINE_2.split(' ');
  const perWord = 0.055;
  const line2Start = words1.length * perWord + 0.15;
  const highlightAt = line2Start + words2.length * perWord + 0.1;

  if (reduced) {
    return (
      <h1 className="t-display center" style={{ margin: 0, maxWidth: '18ch' }}>
        {LINE_1}<br />
        <span style={{ color: 'var(--accent)' }}>{LINE_2}</span>
      </h1>
    );
  }

  return (
    <h1 className="t-display center" style={{ margin: 0, maxWidth: '18ch' }}>
      <span className="sr-only">{LINE_1} {LINE_2}</span>
      <span aria-hidden="true">
        {words1.map((word, i) => (
          <motion.span
            key={`a${i}`}
            style={{ display: 'inline-block', marginRight: '0.28em' }}
            initial={{ opacity: 0, y: 14, filter: 'blur(4px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            transition={{ delay: i * perWord, duration: 0.42, ease: EASE }}
          >
            {word}
          </motion.span>
        ))}
        <br />
        <span style={{ position: 'relative', display: 'inline-block' }}>
          {words2.map((word, i) => (
            <motion.span
              key={`b${i}`}
              style={{ display: 'inline-block', marginRight: '0.28em', color: 'var(--accent)' }}
              initial={{ opacity: 0, y: 14, filter: 'blur(4px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              transition={{ delay: line2Start + i * perWord, duration: 0.42, ease: EASE }}
            >
              {word}
            </motion.span>
          ))}
          {/* highlight-in sweep once the phrase has landed */}
          <motion.span
            aria-hidden="true"
            style={{
              position: 'absolute', left: -6, right: 2, top: '8%', bottom: '10%',
              background: 'linear-gradient(90deg, rgba(76,141,255,.22), rgba(76,141,255,.06))',
              borderRadius: 6, transformOrigin: 'left center', zIndex: -1,
            }}
            initial={{ scaleX: 0, opacity: 0 }}
            animate={{ scaleX: 1, opacity: 1 }}
            transition={{ delay: highlightAt, duration: 0.5, ease: EASE }}
          />
        </span>
      </span>
    </h1>
  );
}

/**
 * The hero diff plays out an injected bug being *applied*: the correct line is
 * struck out, then the buggy line types in beneath it.
 *
 * This is illustrative UI, not live data — it shows challenge-01's real
 * ground-truth bug (`a[mid] < x` becoming `a[mid] <= x` in cpython's
 * bisect_left), which is the actual seeded bug, and is labelled as an example.
 */
const SAMPLE = {
  file: 'Lib/bisect.py',
  fn: 'bisect_left',
  before: '        if a[mid] < x:',
  after: '        if a[mid] <= x:',
  context: [
    ['11', '    while lo < hi:'],
    ['12', '        mid = (lo + hi) // 2'],
  ],
  tail: [
    ['14', '            lo = mid + 1'],
    ['15', '        else:'],
    ['16', '            hi = mid'],
  ],
};

export function HeroDiff() {
  const reduced = useReducedMotion();
  const [phase, setPhase] = useState(reduced ? 2 : 0);

  useEffect(() => {
    if (reduced) return undefined;
    const t1 = setTimeout(() => setPhase(1), 1500);
    const t2 = setTimeout(() => setPhase(2), 2250);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [reduced]);

  const typed = SAMPLE.after;

  return (
    <div className="code-panel" style={{ width: '100%', maxWidth: 720 }}>
      <div className="card-head">
        <div className="code-dots" aria-hidden="true">
          <i style={{ background: '#FF6B6B' }} /><i style={{ background: '#FFB84C' }} /><i style={{ background: '#3DD68C' }} />
        </div>
        <span className="t-code-sm text-dim" style={{ marginLeft: 6 }}>{SAMPLE.file}</span>
        <span className="spacer" />
        <span className="chip chip-accent">
          <span className="dot" /> bug injected
        </span>
      </div>

      <div className="code-scroll">
        {SAMPLE.context.map(([ln, text]) => (
          <div className="code-line" key={ln}><span className="ln">{ln}</span><span className="t-code text-dim">{text}</span></div>
        ))}

        <motion.div
          className={`code-line ${phase >= 1 ? 'code-line-del' : ''}`}
          animate={{ opacity: phase >= 1 ? 0.55 : 1 }}
          transition={{ duration: 0.3, ease: EASE }}
        >
          <span className="ln">13</span>
          <span className="t-code" style={{ color: phase >= 1 ? 'var(--error)' : 'var(--text)', textDecoration: phase >= 1 ? 'line-through' : 'none' }}>
            {phase >= 1 ? `- ${SAMPLE.before.trim()}` : SAMPLE.before}
          </span>
        </motion.div>

        {phase >= 2 && (
          <motion.div
            className="code-line code-line-add"
            initial={reduced ? false : { opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, ease: EASE }}
          >
            <span className="ln">13</span>
            <span className="t-code" style={{ color: 'var(--success)' }}>
              {reduced ? `+ ${typed.trim()}` : <Typewriter text={`+ ${typed.trim()}`} />}
            </span>
          </motion.div>
        )}

        {SAMPLE.tail.map(([ln, text]) => (
          <div className="code-line" key={ln}><span className="ln">{ln}</span><span className="t-code text-dim">{text}</span></div>
        ))}
      </div>

      <div className="row gap-md" style={{ padding: '10px 16px', borderTop: '1px solid var(--border)', background: 'rgba(255,255,255,.015)' }}>
        <span className="t-code-sm text-muted">example: challenge-01 · {SAMPLE.fn}()</span>
        <span className="spacer" />
        <motion.span
          className="chip chip-error"
          initial={{ opacity: 0 }}
          animate={{ opacity: phase >= 2 ? 1 : 0 }}
          transition={{ duration: 0.3, delay: 0.5 }}
        >
          2 of 4 hidden tests now fail
        </motion.span>
      </div>
    </div>
  );
}

function Typewriter({ text, speed = 26 }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setN((v) => (v >= text.length ? (clearInterval(id), v) : v + 1)), speed);
    return () => clearInterval(id);
  }, [text, speed]);
  return (
    <>
      {text.slice(0, n)}
      {n < text.length && <span style={{ opacity: 0.7 }}>▋</span>}
    </>
  );
}
