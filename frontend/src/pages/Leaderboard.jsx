import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { useApp } from '../store.jsx';
import { SkeletonRows } from '../components/Skeleton.jsx';
import { LeaderboardEmpty } from '../components/LeaderboardRows.jsx';
import { LiveDot } from '../components/ActivityFeed.jsx';
import { formatDuration, formatSeconds, NO_DATA } from '../api.js';
import { EASE } from '../motion.js';

export default function Leaderboard() {
  const { leaderboard, stats, challenges, displayName, liveConnected, refreshLeaderboard } = useApp();
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');

  useEffect(() => { refreshLeaderboard(); }, [refreshLeaderboard]);

  const loading = leaderboard === null;

  const rows = useMemo(() => {
    if (!leaderboard) return [];
    return leaderboard.filter((row) => {
      const byChallenge = filter === 'all' || row.challenge_id === filter;
      const q = query.trim().toLowerCase();
      const byQuery = !q || `${row.user_display_name} ${row.challenge_id}`.toLowerCase().includes(q);
      return byChallenge && byQuery;
    });
  }, [leaderboard, filter, query]);

  /* Headline figures are derived from the rows actually returned — not from a
     separate, invented metrics source. With no submissions they read as "—". */
  const best = leaderboard?.length ? Math.max(...leaderboard.map((r) => r.score)) : null;
  const fastestSolve = stats?.fastest_solve_seconds ?? null;
  const myBest = leaderboard?.filter((r) => r.user_display_name === displayName) ?? [];
  const myRank = displayName && leaderboard
    ? leaderboard.findIndex((r) => r.user_display_name === displayName) + 1
    : 0;

  return (
    <div className="shell section-sm">
      <div className="stack gap-md" style={{ marginBottom: 'var(--s-xl)' }}>
        <div className="row gap-sm wrap">
          <span className="eyebrow">Ranked by score, then by time</span>
          <LiveDot connected={liveConnected} label={liveConnected ? 'live · pushed on every submission' : 'reconnecting'} />
        </div>
        <div className="row gap-lg wrap" style={{ alignItems: 'flex-end' }}>
          <div className="stack gap-sm" style={{ flex: 1, minWidth: 280 }}>
            <h1 className="t-headline" style={{ margin: 0 }}>Leaderboard</h1>
            <p className="t-body-lg text-dim measure" style={{ margin: 0 }}>
              Every row is a real scored submission. Correctness comes from hidden test execution; the
              score is the Evaluator Agent's 0–100 rating of the fix.
            </p>
          </div>

          <div className="lb-stats">
            <HeadlineStat label="Submissions scored" value={loading ? null : leaderboard.length} />
            <HeadlineStat label="Highest score" value={best === null ? NO_DATA : best} />
            <HeadlineStat label="Fastest solve" value={formatSeconds(fastestSolve)} />
            <HeadlineStat
              label="Your best rank"
              value={myRank > 0 ? `#${String(myRank).padStart(2, '0')}` : NO_DATA}
              accent={myRank > 0}
              sub={myRank > 0 ? `${myBest.length} scored` : displayName ? 'no entries yet' : 'set a display name'}
            />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head" style={{ height: 'auto', paddingBlock: 10, flexWrap: 'wrap', gap: 8 }}>
          <div className="row gap-xs wrap">
            <FilterChip active={filter === 'all'} onClick={() => setFilter('all')}>All challenges</FilterChip>
            {(challenges || []).map((c) => (
              <FilterChip key={c.challenge_id} active={filter === c.challenge_id} onClick={() => setFilter(c.challenge_id)}>
                {c.function_name}()
              </FilterChip>
            ))}
          </div>
          <span className="spacer" />
          <input
            className="input input-mono"
            style={{ width: 220 }}
            placeholder="Search handle or challenge…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search the leaderboard"
          />
        </div>

        {loading ? (
          <div className="card-body"><SkeletonRows rows={6} /></div>
        ) : rows.length === 0 ? (
          <LeaderboardEmpty
            note={leaderboard.length === 0
              ? 'No submissions have been scored yet.'
              : 'No entries match the current filter.'}
          />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="grid-table">
              <thead>
                <tr>
                  <th style={{ width: 64 }}>Rank</th>
                  <th>Developer</th>
                  <th>Challenge</th>
                  <th style={{ width: 110 }}>Tests</th>
                  <th style={{ width: 90 }}>Time</th>
                  <th style={{ width: 90, textAlign: 'right' }}>Score</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const self = displayName && row.user_display_name === displayName;
                  return (
                    <motion.tr
                      key={`${row.user_display_name}-${row.challenge_id}-${index}`}
                      className={self ? 'row-self' : ''}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: Math.min(index * 0.03, 0.3), duration: 0.25, ease: EASE }}
                    >
                      <td>
                        <span className="t-code" style={{ color: index < 3 ? 'var(--accent)' : 'var(--text-muted)' }}>
                          {String(index + 1).padStart(2, '0')}
                        </span>
                      </td>
                      <td>
                        <div className="row gap-sm">
                          <span className="lb-avatar" aria-hidden="true">
                            {row.user_display_name.slice(0, 2).toUpperCase()}
                          </span>
                          <span style={{ fontWeight: self ? 600 : 400 }}>{row.user_display_name}</span>
                          {self && <span className="chip chip-accent">you</span>}
                        </div>
                      </td>
                      <td><span className="t-code text-dim">{row.challenge_id}</span></td>
                      <td>
                        {row.correct
                          ? <span className="chip chip-success">all passed</span>
                          : <span className="chip chip-error">failed</span>}
                      </td>
                      <td><span className="t-code text-dim">{formatDuration(row.time_taken_seconds)}</span></td>
                      <td style={{ textAlign: 'right' }}>
                        <span className="t-code-lg num">{row.score}</span>
                        <span className="t-code-sm text-muted">/100</span>
                      </td>
                    </motion.tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {!loading && (
          <div className="row gap-md" style={{ padding: '10px 16px', borderTop: '1px solid var(--border)' }}>
            <span className="t-code-sm text-muted">
              {leaderboard.length === 0
                ? 'Awaiting the first scored submission'
                : `Showing ${rows.length} of ${leaderboard.length} scored ${leaderboard.length === 1 ? 'submission' : 'submissions'}`}
            </span>
            <span className="spacer" />
            <Link to="/challenges" className="btn btn-secondary btn-sm">Take a challenge →</Link>
          </div>
        )}
      </div>
    </div>
  );
}

function HeadlineStat({ label, value, sub, accent }) {
  return (
    <div className={`card lb-stat ${accent ? 'lb-stat-accent' : ''}`}>
      <span className="t-label text-dim">{label}</span>
      <span className="num" style={{ font: '500 22px/1.2 var(--font-mono)', color: accent ? 'var(--accent)' : 'var(--text)' }}>
        {value === null ? <span className="sk" style={{ display: 'inline-block', width: 40, height: 18 }} /> : value}
      </span>
      {sub && <span className="t-body-sm text-muted">{sub}</span>}
    </div>
  );
}

function FilterChip({ active, onClick, children }) {
  return (
    <button type="button" onClick={onClick} className={`filter-chip ${active ? 'filter-chip-active' : ''}`}>
      {children}
    </button>
  );
}
