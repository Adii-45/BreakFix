import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from './api.js';

/* One shared fetch of the two catalogue-level resources, so the nav badge, the
   landing stat strip and the challenge grid all read the same real numbers
   instead of each inventing their own. */
const AppContext = createContext(null);
const NAME_KEY = 'breakfix.displayName';

export function AppProvider({ children }) {
  const [challenges, setChallenges] = useState(null);   // null = still loading
  const [stats, setStats] = useState(null);
  const [leaderboard, setLeaderboard] = useState(null);
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

  const value = useMemo(() => ({
    challenges, stats, leaderboard, error, displayName, setDisplayName,
    refreshCatalogue, refreshLeaderboard,
  }), [challenges, stats, leaderboard, error, displayName, refreshCatalogue, refreshLeaderboard]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export const useApp = () => useContext(AppContext);
