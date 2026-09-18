import { useEffect, useState } from 'react';
import { api, NO_DATA, formatCount } from '../api.js';
import { SkeletonLine } from './Skeleton.jsx';

/**
 * Live CloudWatch metrics for the deployed Lambdas (Part 4.2).
 *
 * There is no fabricated fallback. When CloudWatch is unreachable — no
 * credentials, or the stack is not deployed — the panel says exactly that
 * instead of rendering plausible-looking numbers.
 */
export default function SystemStatus() {
  const [state, setState] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.systemStatus()
      .then((data) => { if (!cancelled) setState(data); })
      .catch((err) => { if (!cancelled) setState({ available: false, reason: err.message }); });
    return () => { cancelled = true; };
  }, []);

  return (
    <section className="card">
      <div className="card-head">
        <span className="t-label text-dim">System status · Amazon CloudWatch</span>
        <span className="spacer" />
        {state && (
          <span className={`chip ${state.available ? 'chip-success' : ''}`}>
            {state.available ? `last ${state.window_minutes} min · ${state.region}` : 'unavailable'}
          </span>
        )}
      </div>
      <div className="card-body">
        {state === null ? (
          <div className="status-grid">
            {[0, 1, 2].map((i) => (
              <div key={i} className="stack gap-sm">
                <SkeletonLine w="90px" h={10} /><SkeletonLine w="60px" h={20} />
              </div>
            ))}
          </div>
        ) : !state.available ? (
          <div className="banner banner-note">
            <span>
              <strong>No live metrics.</strong> {state.reason} Nothing is shown here rather than a
              placeholder figure — these numbers are only meaningful against a deployed stack.
            </span>
          </div>
        ) : (
          <div className="status-grid">
            {state.functions.map((fn) => (
              <div key={fn.function_name} className="stack gap-xs">
                <span className="t-label text-dim">{fn.label}</span>
                <span className="num" style={{ font: '500 22px/1.2 var(--font-mono)' }}>
                  {fn.has_data ? formatCount(fn.invocations) : NO_DATA}
                </span>
                <span className="t-body-sm text-muted">
                  {fn.has_data
                    ? `${fn.avg_duration_ms ?? NO_DATA} ms avg · ${fn.errors} error${fn.errors === 1 ? '' : 's'}`
                    : 'no invocations in this window'}
                </span>
                <span className="t-code-sm text-muted">{fn.function_name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
