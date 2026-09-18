import { useEffect, useMemo, useState } from 'react';
import { formatDuration } from '../api.js';

/* F2: the countdown is deliberately cosmetic. The server computes the real
   elapsed time from the session's start_time, so a paused tab or a fiddled
   clock changes what the student sees, never what gets recorded. */
export default function Timer({ startedAt, limitSeconds, onExpire }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, []);

  const remaining = Math.max(0, limitSeconds - (now - startedAt) / 1000);
  const expired = remaining <= 0;

  useEffect(() => {
    if (expired) onExpire?.();
  }, [expired, onExpire]);

  const tone = useMemo(() => {
    const ratio = remaining / limitSeconds;
    if (ratio <= 0.1) return 'danger';
    if (ratio <= 0.33) return 'warn';
    return '';
  }, [remaining, limitSeconds]);

  return (
    <div className={`timer ${tone}`}>
      <span className="label">Time remaining</span>
      <span className="value" aria-hidden="true">{formatDuration(remaining)}</span>
      <span className="sr-only" role="timer" aria-live="off">
        {Math.ceil(remaining)} seconds remaining
      </span>
      <div className="timer-track">
        <div className="timer-fill" style={{ width: `${Math.max(0, (remaining / limitSeconds) * 100)}%` }} />
      </div>
    </div>
  );
}
