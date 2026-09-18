import { formatDuration } from '../api.js';

export default function Leaderboard({ entries, loading }) {
  return (
    <section className="panel" aria-labelledby="lb-head">
      <div className="panel-head">
        <h2 id="lb-head">Leaderboard</h2>
      </div>
      <div className="panel-body">
        {loading && <p className="empty">Loading scores…</p>}
        {!loading && entries.length === 0 && (
          <p className="empty">No attempts yet. The first submission lands here.</p>
        )}
        {entries.length > 0 && (
          <ol className="lb">
            {entries.map((entry, index) => (
              <li key={`${entry.user_display_name}-${entry.challenge_id}-${index}`} className={index < 3 ? 'top' : ''}>
                <span className="rank">{index + 1}</span>
                <span className="who">
                  {entry.user_display_name}
                  <small>{entry.challenge_id}</small>
                </span>
                <span className="pts">{entry.score}</span>
                <span className="secs">{formatDuration(entry.time_taken_seconds)}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
