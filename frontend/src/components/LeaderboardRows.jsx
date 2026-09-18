import { motion } from 'motion/react';
import { formatDuration } from '../api.js';
import { EASE } from '../motion.js';

/** Renders exactly the rows GET /leaderboard returned. Never padded. */
export function LeaderboardList({ entries, highlightName, compact = false }) {
  if (!entries.length) return null;
  return (
    <ol className="lb-list" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
      {entries.map((entry, index) => {
        const self = highlightName && entry.user_display_name === highlightName;
        return (
          <motion.li
            key={`${entry.user_display_name}-${entry.challenge_id}-${index}`}
            className={`lb-row ${self ? 'lb-row-self' : ''}`}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.045, duration: 0.28, ease: EASE }}
          >
            <span className={`lb-rank ${index < 3 ? 'lb-rank-top' : ''}`}>{String(index + 1).padStart(2, '0')}</span>
            <span className="lb-who">
              <span className="lb-name">{entry.user_display_name}</span>
              {!compact && <span className="t-code-sm text-muted">{entry.challenge_id}</span>}
            </span>
            <span className="spacer" />
            {entry.correct
              ? <span className="chip chip-success">pass</span>
              : <span className="chip chip-error">fail</span>}
            <span className="num t-code-lg" style={{ minWidth: 34, textAlign: 'right' }}>{entry.score}</span>
            <span className="num t-code-sm text-muted" style={{ minWidth: 42, textAlign: 'right' }}>
              {formatDuration(entry.time_taken_seconds)}
            </span>
          </motion.li>
        );
      })}
    </ol>
  );
}

/** Honest empty state — the alternative would be inventing names. */
export function LeaderboardEmpty({ note = 'No submissions have been scored yet.' }) {
  return (
    <div className="empty-state">
      <span className="icon" aria-hidden="true">◍</span>
      <span className="t-body" style={{ color: 'var(--text-dim)' }}>{note}</span>
      <span className="t-body-sm text-muted">Rankings appear here as soon as the first fix is evaluated.</span>
    </div>
  );
}
