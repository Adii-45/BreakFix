import { useEffect, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { motion } from 'motion/react';

const LINKS = [
  { to: '/challenges', label: 'Challenges' },
  { to: '/leaderboard', label: 'Leaderboard' },
  { to: '/how-it-works', label: 'How It Works' },
];

export default function Nav({ challengeCount, displayName }) {
  const [scrolled, setScrolled] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className={`nav ${scrolled ? 'nav-scrolled' : ''}`}>
      <div className="shell nav-inner">
        <Link to="/" className="brand" aria-label="BreakFix home">
          <span className="brand-mark" aria-hidden="true">&gt;_</span>
          <span>BreakFix</span>
        </Link>

        <nav className="nav-links" aria-label="Primary">
          {LINKS.map((link) => {
            const active = pathname.startsWith(link.to);
            return (
              <NavLink key={link.to} to={link.to} className={`nav-link ${active ? 'nav-link-active' : ''}`}>
                {link.label}
                {active && <motion.span layoutId="nav-underline" className="nav-underline" />}
              </NavLink>
            );
          })}
        </nav>

        <span className="spacer" />

        <div className="row gap-sm">
          {/* Real count from GET /challenges — never a hardcoded figure. */}
          {challengeCount !== null && (
            <span className="chip chip-success">
              <span className="dot dot-live" />
              {challengeCount} {challengeCount === 1 ? 'challenge' : 'challenges'}
            </span>
          )}
          {displayName && <span className="chip">@{displayName}</span>}
          {!pathname.startsWith('/challenges') && !pathname.startsWith('/results') && (
            <Link to="/challenges" className="btn btn-primary btn-sm">Start Debugging</Link>
          )}
        </div>
      </div>
    </header>
  );
}
