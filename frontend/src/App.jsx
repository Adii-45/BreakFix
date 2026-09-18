import { lazy, Suspense } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Link, Route, Routes, useLocation } from 'react-router-dom';
import Nav from './components/Nav.jsx';
import { AppProvider, useApp } from './store.jsx';
import { pageTransition } from './motion.js';

import Landing from './pages/Landing.jsx';
import Challenges from './pages/Challenges.jsx';
// CodeMirror is the bulk of the bundle and is only needed once an attempt has
// started, so the editor route is split out of the initial load.
const Editor = lazy(() => import('./pages/Editor.jsx'));
import Results from './pages/Results.jsx';
import Leaderboard from './pages/Leaderboard.jsx';
import HowItWorks from './pages/HowItWorks.jsx';
import Admin from './pages/Admin.jsx';

function Shell() {
  const location = useLocation();
  const { challenges, displayName } = useApp();

  return (
    <>
      <div className="ambient" aria-hidden="true" />
      <Nav challengeCount={challenges ? challenges.length : null} displayName={displayName} />

      <main className="app-main">
        <AnimatePresence mode="wait">
          <motion.div key={location.pathname} {...pageTransition}>
            <Suspense fallback={<EditorFallback />}>
            <Routes location={location}>
              <Route path="/" element={<Landing />} />
              <Route path="/challenges" element={<Challenges />} />
              <Route path="/challenges/:sessionId" element={<Editor />} />
              <Route path="/results/:sessionId" element={<Results />} />
              <Route path="/leaderboard" element={<Leaderboard />} />
              <Route path="/how-it-works" element={<HowItWorks />} />
              <Route path="/admin" element={<Admin />} />
              <Route path="*" element={<Landing />} />
            </Routes>
            </Suspense>
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="footer">
        <div className="shell footer-inner">
          <span style={{ color: 'var(--text-dim)' }}>breakfix/core</span>
          <span>·</span>
          <span>AWS Generative AI Hackathon project</span>
          <span className="spacer" />
          <span>Correctness is decided by real test execution, never by an LLM.</span>
          <span>·</span>
          <Link to="/admin" style={{ color: 'var(--text-muted)' }}>admin</Link>
        </div>
      </footer>
    </>
  );
}

/** Shown for the moment the split editor chunk is in flight. */
function EditorFallback() {
  return (
    <div className="shell section-sm">
      <div className="card" style={{ height: 420 }}>
        <div className="card-head"><span className="sk" style={{ width: 140, height: 12 }} /></div>
        <div className="card-body stack gap-md">
          {Array.from({ length: 10 }).map((_, i) => (
            <span key={i} className="sk sk-line" style={{ width: `${90 - i * 6}%` }} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
