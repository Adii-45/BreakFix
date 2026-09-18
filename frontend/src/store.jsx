import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from './api.js';
import { useRealtime } from './realtime.js';

/* One shared fetch of the two catalogue-level resources, so the nav badge, the
   landing stat strip and the challenge grid all read the same real numbers
   instead of each inventing their own. */
const AppContext = createContext(null);
const NAME_KEY = 'breakfix.displayName';

export function AppProvider({ children }) {
  const [challenges, setChallenges] = useState(null);   // null = still loading
  const [stats, setStats] = useState(null);
  const [leaderboard, setLeaderboard] = useState(null);
  const [presence, setPresence] = useState({});     // challenge_id -> real in_progress count
  const [activity, setActivity] = useState(null);   // real recent submissions, newest first
  const [authoring, setAuthoring] = useState(null); // live Step Functions execution state
  const [error, setError] = useState('');
  const [displayName, setDisplayName] = useState(() => {
    try { return localStorage.getItem(NAME_KEY) || ''; } catch { return ''; }
  });

  useEffect(() => {
    try { localStorage.setItem(NAME_KEY, displayName); } catch { /* private mode */ }
  }, [displayName]);

  const refreshCatalogue = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([api.listChallenges(), api.stats()]);
      setChallenges(c.challenges || []);
      setStats(s);
      setError('');
    } catch (err) {
      setChallenges([]);
      setError(err.message);
    }
  }, []);

  const refreshLeaderboard = useCallback(async () => {
    try {
      const data = await api.leaderboard();
      setLeaderboard(data.leaderboard || []);
    } catch {
      setLeaderboard([]);
    }
  }, []);

  useEffect(() => { refreshCatalogue(); refreshLeaderboard(); }, [refreshCatalogue, refreshLeaderboard]);

  /* Live layer. Every field below is replaced only by what the server pushes;
     nothing here fabricates a count or an event when the socket is quiet. */
  const applyPayload = useCallback((payload) => {
    if (!payload || typeof payload !== 'object') return;
    if (Array.isArray(payload.leaderboard)) setLeaderboard(payload.leaderboard);
    if (payload.presence && typeof payload.presence === 'object') setPresence(payload.presence);
    if (Array.isArray(payload.activity)) setActivity(payload.activity);
    if (payload.type === 'authoring' && payload.execution) setAuthoring(payload.execution);
    if (payload.type === 'event' && payload.detail_type === 'challenge.published') {
      // An EventBridge announcement, not a table write: refresh the catalogue.
      refreshCatalogue();
    }
    if (payload.type === 'update' && Array.isArray(payload.activity)) {
      // A Results write also moves the per-challenge attempt counters.
      refreshCatalogue();
    }
  }, [refreshCatalogue]);

  const { connected: liveConnected, refresh: refreshLive } = useRealtime(applyPayload);

  const value = useMemo(() => ({
    challenges, stats, leaderboard, presence, activity, authoring, error,
    displayName, setDisplayName, liveConnected,
    refreshCatalogue, refreshLeaderboard, refreshLive,
  }), [challenges, stats, leaderboard, presence, activity, authoring, error, displayName,
       liveConnected, refreshCatalogue, refreshLeaderboard, refreshLive]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export const useApp = () => useContext(AppContext);
