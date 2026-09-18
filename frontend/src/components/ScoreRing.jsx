import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { EASE } from '../motion.js';

/**
 * Animates its stroke from 0 to the REAL score returned by the API.
 * `score` is the Evaluator Agent's 0-100 quality rating (PRD 8.2) — it is not
 * recomputed here from any client-side formula.
 */
export default function ScoreRing({ score, passed, size = 188, stroke = 10 }) {
  const reduced = useReducedMotion();
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const value = Math.max(0, Math.min(100, Number(score) || 0));
  const tone = passed ? 'var(--success)' : 'var(--error)';
  const displayed = useCountUp(value, reduced);

  return (
    <div style={{ position: 'relative', width: size, height: size, flex: 'none' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--border)" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={tone}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - value / 100) }}
          transition={reduced ? { duration: 0 } : { duration: 1.1, ease: EASE, delay: 0.15 }}
          style={{ filter: `drop-shadow(0 0 10px ${passed ? 'rgba(61,214,140,.35)' : 'rgba(255,107,107,.35)'})` }}
        />
      </svg>

      <div
        className="stack"
        style={{ position: 'absolute', inset: 0, alignItems: 'center', justifyContent: 'center' }}
      >
        <motion.div
          className="row"
          style={{ alignItems: 'baseline', gap: 2 }}
          initial={reduced ? false : { opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3, ease: EASE }}
        >
          <span className="num" style={{ font: '600 46px/1 var(--font-mono)', color: 'var(--text)' }}>
            {displayed}
          </span>
          <span className="t-code-lg text-muted">/100</span>
        </motion.div>
        <span className={`chip ${passed ? 'chip-success' : 'chip-error'}`} style={{ marginTop: 10 }}>
          {passed ? 'Tests passed' : 'Tests failed'}
        </span>
      </div>
    </div>
  );
}

/** Ticks the real score up from 0 rather than snapping to it. */
function useCountUp(target, reduced) {
  const [value, setValue] = useState(reduced ? target : 0);
  useEffect(() => {
    if (reduced) { setValue(target); return undefined; }
    const duration = 1100;
    const start = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const t = Math.min(1, (now - start) / duration);
      setValue(Math.round(target * (1 - Math.pow(1 - t, 3))));  // ease-out cubic
      if (t < 1) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [target, reduced]);
  return value;
}
