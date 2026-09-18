import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { EASE } from '../motion.js';

/**
 * Server-authoritative countdown.
 *
 * `startTime` is the epoch second the Sessions row was written (PRD 6.2), so the
 * clock is anchored to the server, not to when this component mounted. It stays
 * cosmetic regardless: `time_taken_seconds` on the result is computed server-side
 * from that same start_time, so nothing here can be gamed for score.
 */
export default function Countdown({ startTime, limitSeconds, onExpire }) {
  const reduced = useReducedMotion();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(id);
  }, []);

  const elapsed = Math.max(0, now / 1000 - startTime);
  const remaining = Math.max(0, limitSeconds - elapsed);
  const expired = remaining <= 0;

  useEffect(() => { if (expired) onExpire?.(); }, [expired, onExpire]);

  const danger = remaining <= 60;
  const warn = !danger && remaining <= limitSeconds * 0.34;
  const tone = danger ? 'var(--error)' : warn ? 'var(--warning)' : 'var(--text)';

  const mm = String(Math.floor(remaining / 60)).padStart(2, '0');
  const ss = String(Math.floor(remaining % 60)).padStart(2, '0');
  const digits = useMemo(() => `${mm}:${ss}`.split(''), [mm, ss]);

  return (
    <div className="card card-pad stack gap-md">
      <div className="row gap-sm">
        <span className="t-label text-dim">Time remaining</span>
        <span className="spacer" />
        <span className="chip" style={{ color: tone, borderColor: 'var(--border)' }}>
          {Math.round(limitSeconds / 60)} min cap
        </span>
      </div>

      <motion.div
        className="row"
        style={{ gap: 1, color: tone }}
        animate={danger && !reduced ? { scale: [1, 1.035, 1] } : { scale: 1 }}
        transition={danger && !reduced ? { duration: 1, repeat: Infinity, ease: 'easeInOut' } : { duration: 0.2 }}
        aria-hidden="true"
      >
        {digits.map((char, index) => (
          <span key={index} style={{ position: 'relative', width: char === ':' ? 14 : 30, height: 46, overflow: 'hidden' }}>
            <AnimatePresence initial={false} mode="popLayout">
              <motion.span
                key={char + index}
                initial={reduced ? false : { y: -30, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={reduced ? { opacity: 0 } : { y: 30, opacity: 0 }}
                transition={{ duration: 0.22, ease: EASE }}
                style={{
                  position: 'absolute', inset: 0,
                  display: 'grid', placeItems: 'center',
                  font: '500 38px/1 var(--font-mono)', fontVariantNumeric: 'tabular-nums',
                }}
              >
                {char}
              </motion.span>
            </AnimatePresence>
          </span>
        ))}
      </motion.div>
      <span className="sr-only" role="timer">{Math.ceil(remaining)} seconds remaining</span>

      <div style={{ height: 4, borderRadius: 'var(--r-pill)', background: 'var(--border)', overflow: 'hidden' }}>
        <motion.div
          style={{ height: '100%', background: tone, borderRadius: 'var(--r-pill)' }}
          animate={{ width: `${Math.max(0, (remaining / limitSeconds) * 100)}%` }}
          transition={{ duration: 0.2, ease: 'linear' }}
        />
      </div>

      <p className="t-body-sm text-muted" style={{ margin: 0 }}>
        Elapsed time is recomputed server-side from your session start, so this clock is for pacing only.
      </p>
    </div>
  );
}
