import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { HeroDiff, HeroHeadline } from '../components/Hero.jsx';
import { Reveal, RevealGroup, RevealItem } from '../components/Reveal.jsx';
import { SkeletonStat } from '../components/Skeleton.jsx';
import { useApp } from '../store.jsx';
import ActivityFeed from '../components/ActivityFeed.jsx';
import { EASE, springTactile } from '../motion.js';
import { NO_DATA, formatCount, formatSeconds } from '../api.js';

/* PRD 5.4 — role text here is the service's actual job in this codebase. */
const AWS_SERVICES = [
  { name: 'Amazon Bedrock', role: 'Runs both agents: the Bug Injector offline, the Evaluator on every submission.', tag: 'Foundation models' },
  { name: 'AWS Lambda', role: 'All backend compute, plus an isolated Test Runner with no IAM permissions.', tag: 'Python 3.12 · arm64' },
  { name: 'Amazon DynamoDB', role: 'Challenges, Sessions and Results tables, with a GSI backing the leaderboard.', tag: 'On-demand capacity' },
  { name: 'Amazon API Gateway', role: 'REST endpoints between the frontend and Lambda, with request throttling.', tag: 'REST · proxy integration' },
  { name: 'AWS Amplify Hosting', role: 'Builds and hosts this frontend, and gives the deployment its public URL.', tag: 'Static hosting' },
];

const PHASES = [
  {
    n: 'Phase 01',
    title: 'An AI agent injects the bug',
    body: 'Amazon Bedrock takes a correct function from a real repository and introduces exactly one realistic, non-trivial defect, along with a structured explanation of what it broke.',
    foot: 'Bug Injector Agent',
    note: 'Discarded unless a hidden test fails',
    tone: 'var(--accent)',
  },
  {
    n: 'Phase 02',
    title: 'You fix it against the clock',
    body: 'The buggy function opens in the editor with a countdown. Read the code, form a hypothesis, make the smallest change that actually addresses the cause.',
    foot: 'Server-authoritative timer',
    note: 'Elapsed time computed from session start',
    tone: 'var(--text-dim)',
  },
  {
    n: 'Phase 03',
    title: 'Hidden tests decide, then AI explains',
    body: 'Your submission runs against hidden unit tests in a sandboxed Lambda. That result is the verdict. Only then does a second agent score how you approached the problem.',
    foot: 'Test Runner → Evaluator Agent',
    note: 'Deterministic first, qualitative second',
    tone: 'var(--success)',
  },
];

export default function Landing() {
  const { stats, challenges, activity, liveConnected } = useApp();
  const loading = stats === null;

  /* Every figure below is a field from GET /stats. Where there is genuinely no
     data yet (no submissions), the API returns null and we render an em dash
     rather than a zero dressed up as activity. */
  const STATS = [
    { k: 'Challenges available', v: stats ? formatCount(stats.challenges_available) : null, sub: stats ? `${stats.repos_covered} open-source repos` : '' },
    { k: 'Hidden tests', v: stats ? formatCount(stats.hidden_tests_total) : null, sub: 'across the seed set' },
    { k: 'Submissions evaluated', v: stats ? formatCount(stats.submissions_evaluated) : null, sub: stats ? `${formatCount(stats.submissions_solved)} solved` : '' },
    { k: 'Median solve time', v: stats ? formatSeconds(stats.median_solve_seconds) : null, sub: stats && stats.fastest_solve_seconds !== null ? `fastest ${formatSeconds(stats.fastest_solve_seconds)}` : 'no solves recorded yet' },
  ];

  return (
    <>
      {/* ---------------------------------------------------------------- hero */}
      <section className="shell stack center" style={{ paddingTop: 'var(--s-4xl)', paddingBottom: 'var(--s-3xl)', alignItems: 'center', gap: 'var(--s-xl)' }}>
        <motion.span
          className="eyebrow"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: EASE }}
        >
          <span className="dot dot-live" style={{ color: 'var(--success)' }} />
          Real open-source repos · sandboxed execution
        </motion.span>

        <HeroHeadline />

        <motion.p
          className="t-body-lg text-dim center measure"
          style={{ margin: 0 }}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.75, duration: 0.45, ease: EASE }}
        >
          Real open-source functions with AI-injected bugs. Hidden test suites verify your fix by
          actually running it, while a second agent scores your debugging methodology.
        </motion.p>

        <motion.div
          className="row gap-md wrap"
          style={{ justifyContent: 'center' }}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.9, duration: 0.45, ease: EASE }}
        >
          <motion.div whileHover={{ y: -1 }} whileTap={{ y: 0 }} transition={springTactile}>
            <Link to="/challenges" className="btn btn-primary btn-lg">Start debugging →</Link>
          </motion.div>
          <motion.div whileHover={{ y: -1 }} whileTap={{ y: 0 }} transition={springTactile}>
            <Link to="/how-it-works" className="btn btn-secondary btn-lg">Inspect architecture</Link>
          </motion.div>
        </motion.div>

        <motion.div
          style={{ width: '100%', display: 'flex', justifyContent: 'center', marginTop: 'var(--s-lg)' }}
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.0, duration: 0.55, ease: EASE }}
        >
          <HeroDiff />
        </motion.div>
      </section>

      {/* --------------------------------------------------------- stat strip */}
      <section className="shell">
        <RevealGroup className="stat-strip card">
          {STATS.map((stat) => (
            <RevealItem key={stat.k} className="stat-cell">
              {loading ? <SkeletonStat /> : (
                <>
                  <span className="t-label text-dim">{stat.k}</span>
                  <span className="num" style={{ font: '500 28px/1.1 var(--font-mono)' }}>{stat.v ?? NO_DATA}</span>
                  <span className="t-body-sm text-muted">{stat.sub}</span>
                </>
              )}
            </RevealItem>
          ))}
        </RevealGroup>
      </section>

      {/* -------------------------------------------------- live activity */}
      <section className="shell" style={{ paddingTop: 'var(--s-2xl)' }}>
        <Reveal>
          <ActivityFeed
            events={activity}
            connected={liveConnected}
            limit={5}
            title="Live activity · pushed over WebSocket"
          />
        </Reveal>
      </section>

      {/* ------------------------------------------------------------- phases */}
      <section className="shell section">
        <Reveal className="stack gap-md" style={{ alignItems: 'center', marginBottom: 'var(--s-2xl)' }}>
          <span className="eyebrow">Workflow</span>
          <h2 className="t-headline center" style={{ margin: 0, maxWidth: '22ch' }}>
            Deterministic execution meets probabilistic critique
          </h2>
          <p className="t-body-lg text-dim center measure" style={{ margin: 0 }}>
            Most code assessment either grades syntax blindly or leans on a model's opinion. BreakFix
            splits the two apart: binary validation from real tests, qualitative critique from an agent.
          </p>
        </Reveal>

        <RevealGroup className="phase-grid" staggerChildren={0.08}>
          {PHASES.map((phase) => (
            <RevealItem key={phase.n}>
              <motion.article
                className="card phase-card"
                whileHover={{ y: -1, borderColor: 'rgba(255, 153, 0, 0.4)', boxShadow: 'var(--elev-2)' }}
                transition={springTactile}
              >
                <div className="card-body stack gap-md">
                  <span className="t-label" style={{ color: phase.tone }}>{phase.n}</span>
                  <h3 className="t-subtitle" style={{ margin: 0 }}>{phase.title}</h3>
                  <p className="t-body text-dim" style={{ margin: 0 }}>{phase.body}</p>
                  <div className="row gap-sm wrap" style={{ marginTop: 'auto', paddingTop: 'var(--s-md)' }}>
                    <span className="t-code-sm text-muted">{phase.foot}</span>
                    <span className="spacer" />
                    <span className="t-code-sm" style={{ color: phase.tone }}>{phase.note}</span>
                  </div>
                </div>
              </motion.article>
            </RevealItem>
          ))}
        </RevealGroup>
      </section>

      {/* ---------------------------------------------------------- principle */}
      <section className="shell section-sm">
        <div className="principle-grid">
          <Reveal className="stack gap-lg">
            <span className="eyebrow">Zero hallucination principle</span>
            <h2 className="t-headline" style={{ margin: 0 }}>
              Correctness is decided by real test execution — never by an LLM's opinion.
            </h2>
            <p className="t-body-lg text-dim" style={{ margin: 0 }}>
              Language models can be talked into approving code that looks plausible but is subtly wrong,
              and one bad call in a live demo discredits everything else on screen. So the pass/fail verdict
              comes from executing hidden unit tests in a sandbox. The Evaluator Agent is handed that result
              as a fact it is not allowed to contradict.
            </p>
            <div className="row gap-sm wrap">
              <span className="chip chip-success"><span className="dot" /> Sandboxed execution</span>
              <span className="chip">Hard 5s timeout</span>
              <span className="chip">No network · no filesystem</span>
            </div>
          </Reveal>

          <Reveal delay={0.1}>
            <div className="code-panel">
              <div className="card-head">
                <span className="t-code-sm text-dim">verdict pipeline</span>
                <span className="spacer" />
                <span className="chip chip-accent">deterministic</span>
              </div>
              <div className="card-body stack gap-md">
                <FlowRow tone="var(--success)" step="1" title="Test Runner (AWS Lambda)"
                  body="Executes your submission against the hidden tests. Produces tests_passed / tests_total." />
                <FlowRow tone="var(--success)" step="2" title="correct = tests_passed == tests_total"
                  body="A boolean computed in code, before any model is called." mono />
                <FlowRow tone="var(--accent)" step="3" title="Evaluator Agent (Bedrock)"
                  body="Receives that outcome as input. Writes feedback and a 0-100 quality score." />
                <div className="banner banner-accent" style={{ marginTop: 4 }}>
                  The agent returns no correctness field at all, and its score is clamped into the band the
                  verdict allows. It cannot flip a fail into a pass.
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* --------------------------------------------------------------- AWS */}
      <section className="shell section">
        <Reveal className="stack gap-md" style={{ alignItems: 'center', marginBottom: 'var(--s-2xl)' }}>
          <span className="eyebrow">Cloud infrastructure</span>
          <h2 className="t-headline center" style={{ margin: 0 }}>Built on AWS, end to end</h2>
          <p className="t-body-lg text-dim center measure" style={{ margin: 0 }}>
            Each service below has a specific job in the running system, not a logo on a slide.
          </p>
        </Reveal>

        <RevealGroup className="aws-grid" staggerChildren={0.07}>
          {AWS_SERVICES.map((service) => (
            <RevealItem key={service.name}>
              <motion.div
                className="card aws-card"
                whileHover={{ y: -1, borderColor: 'rgba(255, 153, 0, 0.4)', boxShadow: 'var(--elev-2)' }}
                transition={springTactile}
              >
                <div className="card-body stack gap-sm" style={{ height: '100%' }}>
                  <h3 className="t-subtitle" style={{ margin: 0, fontSize: 14 }}>{service.name}</h3>
                  <p className="t-body-sm text-dim" style={{ margin: 0, flex: 1 }}>{service.role}</p>
                  <span className="t-code-sm text-muted" style={{ marginTop: 'var(--s-sm)' }}>{service.tag}</span>
                </div>
              </motion.div>
            </RevealItem>
          ))}
        </RevealGroup>
      </section>

      {/* --------------------------------------------------------------- CTA */}
      <section className="shell" style={{ paddingBottom: 'var(--s-2xl)' }}>
        <Reveal>
          <div className="card cta-card">
            <div className="stack gap-sm">
              <span className="t-label text-accent">Ready when you are</span>
              <h2 className="t-title" style={{ margin: 0 }}>Test your diagnostic instincts</h2>
              <p className="t-body text-dim" style={{ margin: 0 }}>
                {challenges && challenges.length > 0
                  ? `${challenges.length} seeded ${challenges.length === 1 ? 'challenge' : 'challenges'} across ${stats?.repos_covered ?? '—'} real repositories. The clock starts on your first keystroke-free read.`
                  : 'Load the challenge list to begin.'}
              </p>
            </div>
            <span className="spacer" />
            <motion.div whileHover={{ y: -1 }} whileTap={{ y: 0 }} transition={springTactile}>
              <Link to="/challenges" className="btn btn-primary btn-lg">Browse challenges →</Link>
            </motion.div>
          </div>
        </Reveal>
      </section>
    </>
  );
}

function FlowRow({ tone, step, title, body, mono }) {
  return (
    <div className="row gap-md" style={{ alignItems: 'flex-start' }}>
      <span
        className="t-label"
        style={{
          color: tone, border: `1px solid ${tone}`, borderRadius: 'var(--r-nested)',
          padding: '3px 7px', flex: 'none', opacity: 0.9,
        }}
      >
        {step}
      </span>
      <div className="stack" style={{ gap: 2 }}>
        <span className={mono ? 't-code' : 't-body'} style={{ color: 'var(--text)' }}>{title}</span>
        <span className="t-body-sm text-muted">{body}</span>
      </div>
    </div>
  );
}
