import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import Pipeline from '../components/Pipeline.jsx';
import SystemStatus from '../components/SystemStatus.jsx';
import { Reveal, RevealGroup, RevealItem } from '../components/Reveal.jsx';
import { useApp } from '../store.jsx';
import { springTactile } from '../motion.js';

/* PRD Section 5.4 — the mandatory-compliance mapping, stated as it is in the
   document and as the deployed stack actually uses each service. */
const SERVICE_MATRIX = [
  {
    name: 'Amazon Bedrock',
    role: 'Runs both the Bug Injector Agent and the Evaluator Agent (foundation model calls).',
    detail: 'Injection happens offline, once per challenge. Evaluation runs live on every submission, after the tests.',
    tag: 'Two agents · distinct tasks',
  },
  {
    name: 'AWS Lambda',
    role: 'All backend compute: challenge serving, diff capture, agent orchestration, leaderboard queries.',
    detail: 'Plus a separate Test Runner function whose execution role grants no permissions at all.',
    tag: 'Python 3.12 · arm64',
  },
  {
    name: 'Amazon API Gateway',
    role: 'REST endpoints between the frontend and Lambda.',
    detail: 'Five routes, with burst and rate throttling so the write endpoints are not left open.',
    tag: 'REST · proxy integration',
  },
  {
    name: 'Amazon DynamoDB',
    role: 'Sessions, Challenges and Results tables.',
    detail: 'The leaderboard is a derived read over Results via a score GSI — there is no second write path.',
    tag: 'PAY_PER_REQUEST',
  },
  {
    name: 'AWS Amplify Hosting',
    role: 'Deploys and hosts the frontend; gives the project a live URL.',
    detail: 'Built from this repository with the build spec committed alongside it.',
    tag: 'Static hosting · CDN',
  },
  {
    name: 'API Gateway WebSocket API',
    role: 'Carries the live layer: leaderboard, presence and the activity feed.',
    detail: 'Clients get a snapshot on connect, then receive pushes. Nothing polls.',
    tag: '$connect · $disconnect · $default',
  },
  {
    name: 'Amazon DynamoDB Streams',
    role: 'Triggers the broadcaster whenever Sessions or Results is written.',
    detail: 'This is what makes the live layer event-driven rather than a polling loop.',
    tag: 'NEW_AND_OLD_IMAGES',
  },
  {
    name: 'AWS Step Functions',
    role: 'Orchestrates live challenge authoring, one state per gate.',
    detail: 'Fetch, author tests, verify against clean, inject, verify the bug bites, golden-set, brief, land in pending_review.',
    tag: 'STANDARD workflow',
  },
  {
    name: 'Amazon EventBridge',
    role: 'Carries domain events — a challenge published, a new high score.',
    detail: 'Decouples announcements from the write path, so consumers are added as rules rather than code edits.',
    tag: 'breakfix-events bus',
  },
  {
    name: 'Amazon CloudWatch',
    role: 'Source of the system-status panel above.',
    detail: 'Invocation counts and average durations for the submit, Test Runner and broadcaster functions.',
    tag: 'AWS/Lambda metrics',
  },
];

const SANDBOX_CONTROLS = [
  ['Separate process', 'Spawned as an isolated interpreter in its own process group.'],
  ['Hard wall-clock timeout', 'The parent kills the whole process group after 5 seconds.'],
  ['Per-test timeout', 'A 2-second alarm around each individual test call.'],
  ['CPU and memory caps', 'RLIMIT_CPU and RLIMIT_AS, plus the Lambda memory ceiling.'],
  ['No network', 'An audit hook blocks every socket event; the socket module is neutered first.'],
  ['No filesystem', 'Only a per-run scratch directory is writable; only the stdlib is readable.'],
  ['No process creation', 'subprocess, os.exec, os.fork and os.system are all blocked.'],
  ['No blast radius', 'The Test Runner Lambda has no IAM policies, so an escape reaches nothing.'],
];

export default function HowItWorks() {
  const { stats } = useApp();

  return (
    <div className="section-sm">
      {/* ------------------------------------------------------------- intro */}
      <section className="shell stack center" style={{ alignItems: 'center', gap: 'var(--s-lg)', marginBottom: 'var(--s-3xl)' }}>
        <Reveal><span className="eyebrow">Architecture</span></Reveal>
        <Reveal delay={0.05}>
          <h1 className="t-headline center" style={{ margin: 0, maxWidth: '24ch' }}>
            Two AI agents. One deterministic sandbox.
          </h1>
        </Reveal>
        <Reveal delay={0.1}>
          <p className="t-body-lg text-dim center measure" style={{ margin: 0 }}>
            Generative mutation is deliberately kept apart from deterministic execution, so a model is
            never in a position to decide whether your code is correct.
          </p>
        </Reveal>
        <Reveal delay={0.15}>
          <div className="row gap-sm wrap" style={{ justifyContent: 'center' }}>
            <span className="chip chip-success"><span className="dot" /> Deterministic verdict</span>
            <span className="chip chip-accent">Two isolated agents</span>
            <span className="chip">Hidden test suites</span>
            {stats && <span className="chip">{stats.hidden_tests_total} tests across {stats.challenges_available} challenges</span>}
          </div>
        </Reveal>
      </section>

      {/* ---------------------------------------------------------- pipeline */}
      <section className="shell" style={{ marginBottom: 'var(--s-4xl)' }}>
        <Reveal className="stack gap-sm" style={{ marginBottom: 'var(--s-lg)' }}>
          <span className="t-label text-dim">System lifecycle</span>
          <h2 className="t-title" style={{ margin: 0 }}>End-to-end orchestration loop</h2>
        </Reveal>
        <Pipeline />
      </section>

      {/* --------------------------------------------------------- principle */}
      <section className="shell" style={{ marginBottom: 'var(--s-4xl)' }}>
        <Reveal>
          <div className="card tenet">
            <div className="card-body stack gap-lg">
              <span className="t-label text-accent">Architectural tenet</span>
              <blockquote className="tenet-quote">
                “Correctness is decided by real test execution. It is never decided by asking an AI model
                whether code looks right.”
              </blockquote>
              <div className="tenet-cols">
                <p className="t-body text-dim" style={{ margin: 0 }}>
                  An earlier version of this design asked the Evaluator Agent to judge correctness from
                  reading the code. That is unreliable: models can be persuaded by code that looks
                  plausible but is subtly wrong, and a single bad call in a live demo undermines the whole
                  pitch.
                </p>
                <p className="t-body text-dim" style={{ margin: 0 }}>
                  Real test execution makes “correct” a defensible fact, and one that a well-worded but
                  incorrect submission cannot game. The agents are kept to what they are genuinely good
                  at: inventing a plausible bug, and explaining fix quality in natural language.
                </p>
              </div>
              <div className="row gap-sm wrap">
                <span className="chip">correct = tests_passed == tests_total</span>
                <span className="chip chip-accent">score clamped to the verdict's band</span>
                <span className="chip">agent returns no correctness field</span>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ----------------------------------------------------------- sandbox */}
      <section className="shell" style={{ marginBottom: 'var(--s-4xl)' }}>
        <div className="sandbox-grid">
          <Reveal className="stack gap-md">
            <span className="t-label text-dim">Threat model</span>
            <h2 className="t-title" style={{ margin: 0 }}>Submitted code is untrusted, and treated that way</h2>
            <p className="t-body text-dim" style={{ margin: 0 }}>
              Every submission is arbitrary code executing on our infrastructure. The Test Runner is a
              CPython audit-hook sandbox inside a disposable Lambda execution environment — not a
              container per submission, and we do not claim otherwise.
            </p>
            <p className="t-body text-dim" style={{ margin: 0 }}>
              That is precisely why the Test Runner runs as its own function with an empty policy set: the
              layer protecting the data does not depend on the sandbox holding.
            </p>
            <div className="row gap-sm wrap">
              <span className="chip">AWS Lambda runs on Firecracker microVMs</span>
            </div>
          </Reveal>

          <RevealGroup className="card sandbox-list" staggerChildren={0.05}>
            {SANDBOX_CONTROLS.map(([title, body]) => (
              <RevealItem key={title} className="sandbox-row">
                <span className="sandbox-check" aria-hidden="true">✓</span>
                <div className="stack" style={{ gap: 1 }}>
                  <span className="t-body" style={{ fontWeight: 500 }}>{title}</span>
                  <span className="t-body-sm text-muted">{body}</span>
                </div>
              </RevealItem>
            ))}
          </RevealGroup>
        </div>
      </section>

      {/* -------------------------------------------------- system status */}
      <section className="shell" style={{ marginBottom: 'var(--s-4xl)' }}>
        <Reveal className="stack gap-sm" style={{ marginBottom: 'var(--s-lg)' }}>
          <span className="t-label text-dim">Operational telemetry</span>
          <h2 className="t-title" style={{ margin: 0 }}>What the stack is actually doing</h2>
          <p className="t-body text-dim measure" style={{ margin: 0 }}>
            Pulled from CloudWatch for the deployed functions. If it is not deployed, this panel says so.
          </p>
        </Reveal>
        <Reveal delay={0.05}><SystemStatus /></Reveal>
      </section>

      {/* --------------------------------------------------------------- AWS */}
      <section className="shell" style={{ marginBottom: 'var(--s-3xl)' }}>
        <Reveal className="stack gap-sm" style={{ marginBottom: 'var(--s-lg)' }}>
          <span className="t-label text-dim">Cloud infrastructure</span>
          <h2 className="t-title" style={{ margin: 0 }}>AWS service roles</h2>
          <p className="t-body text-dim measure" style={{ margin: 0 }}>
            The mandatory-compliance mapping, stated so it is auditable at a glance.
          </p>
        </Reveal>

        <RevealGroup className="stack" staggerChildren={0.06}>
          {SERVICE_MATRIX.map((service, i) => (
            <RevealItem key={service.name}>
              <motion.div
                className="card service-row"
                whileHover={{ borderColor: 'rgba(76, 141, 255, 0.4)', boxShadow: 'var(--elev-2)' }}
                transition={springTactile}
                style={{ marginTop: i === 0 ? 0 : 'var(--s-sm)' }}
              >
                <div className="card-body service-body">
                  <div className="stack" style={{ gap: 3, minWidth: 190 }}>
                    <span className="t-subtitle" style={{ fontSize: 14 }}>{service.name}</span>
                    <span className="t-code-sm text-muted">{service.tag}</span>
                  </div>
                  <div className="stack" style={{ gap: 3, flex: 1, minWidth: 260 }}>
                    <span className="t-body">{service.role}</span>
                    <span className="t-body-sm text-muted">{service.detail}</span>
                  </div>
                </div>
              </motion.div>
            </RevealItem>
          ))}
        </RevealGroup>
      </section>

      <section className="shell">
        <Reveal>
          <div className="card cta-card">
            <div className="stack gap-sm">
              <span className="t-label text-accent">See it run</span>
              <h2 className="t-title" style={{ margin: 0 }}>Put the pipeline to work</h2>
              <p className="t-body text-dim" style={{ margin: 0 }}>
                Pick a function, find the injected bug, and watch the verdict come back from real test
                execution.
              </p>
            </div>
            <span className="spacer" />
            <motion.div whileHover={{ y: -1 }} whileTap={{ y: 0 }} transition={springTactile}>
              <Link to="/challenges" className="btn btn-primary btn-lg">Try a challenge →</Link>
            </motion.div>
          </div>
        </Reveal>
      </section>
    </div>
  );
}
