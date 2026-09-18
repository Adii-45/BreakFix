import { AnimatePresence, motion } from 'motion/react';
import { relativeTime } from '../realtime.js';
import { formatDuration } from '../api.js';
import { EASE } from '../motion.js';
import { SkeletonRows } from './Skeleton.jsx';

/**
 * Real recent submissions, pushed over the WebSocket as they are written to the
 * Results table. Shows exactly as many events as have genuinely happened — two
 * real events render as two rows, never padded out to fill the panel.
 */
export default function ActivityFeed({ events, connected, limit = 6, title = 'Live activity' }) {
  const rows = (events || []).slice(0, limit);

  return (
    <section className="card">
      <div className="card-head">
        <span className="t-label text-dim">{title}</span>
        <span className="spacer" />
        <LiveDot connected={connected} />
      </div>
      <div className="card-body" style={{ paddingTop: rows.length ? 8 : 16 }}>
        {events === null ? (
          <SkeletonRows rows={3} height={40} />
        ) : rows.length === 0 ? (
          <div className="empty-state" style={{ padding: 'var(--s-lg) 0' }}>
            <span className="t-body" style={{ color: 'var(--text-dim)' }}>No submissions yet.</span>
            <span className="t-body-sm text-muted">Events appear here the moment someone submits a fix.</span>
          </div>
        ) : (
          <ul className="feed" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            <AnimatePresence initial={false}>
              {rows.map((event) => (
                <motion.li
                  key={event.session_id}
                  className="feed-row"
                  layout
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.28, ease: EASE }}
                >
                  <span className={`feed-pip ${event.correct ? 'is-pass' : 'is-fail'}`} aria-hidden="true" />
                  <div className="stack" style={{ gap: 1, minWidth: 0 }}>
                    <span className="t-body" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <strong>{event.user_display_name}</strong>{' '}
                      {event.correct ? 'solved' : 'attempted'}{' '}
                      <span className="t-code" style={{ color: 'var(--accent)' }}>
                        {event.function_name ? `${event.function_name}()` : event.challenge_id}
                      </span>
                      {event.correct && ` in ${formatDuration(event.time_taken_seconds)}`}
                    </span>
                    <span className="t-code-sm text-muted">
                      {event.tests_passed}/{event.tests_total} tests · score {event.score} · {relativeTime(event.at)}
                    </span>
                  </div>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </section>
  );
}

export function LiveDot({ connected, label }) {
  return (
    <span className={`chip ${connected ? 'chip-success' : ''}`} title={connected ? 'WebSocket connected' : 'Reconnecting…'}>
      <span className={`dot ${connected ? 'dot-live' : ''}`} style={{ color: connected ? 'var(--success)' : 'var(--text-muted)' }} />
      {label || (connected ? 'live' : 'reconnecting')}
    </span>
  );
}

/** "N solving now" — a real count of in_progress sessions, or nothing at all. */
export function PresenceBadge({ count }) {
  if (!count) return null;   // zero renders as absent, never as "0 people"
  return (
    <motion.span
      className="chip chip-accent"
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25, ease: EASE }}
    >
      <span className="dot dot-live" style={{ color: 'var(--accent)' }} />
      {count} solving now
    </motion.span>
  );
}
