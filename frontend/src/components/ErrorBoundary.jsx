import { Component } from 'react';
import { Link } from 'react-router-dom';

/**
 * Without this, a single render throw blanks the whole page and the only way
 * back is for whoever is driving to know to reload. A judge clicking around
 * would just see black.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Keep the detail in the console for whoever is debugging the demo.
    console.error('BreakFix render error:', error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="shell section-sm">
        <div className="card">
          <div className="card-head"><span className="t-label text-dim">Something broke</span></div>
          <div className="card-body stack gap-lg">
            <div className="stack gap-sm">
              <h1 className="t-title" style={{ margin: 0 }}>This screen hit an error</h1>
              <p className="t-body text-dim" style={{ margin: 0 }}>
                The rest of the app is fine — your submitted results are stored server-side and the
                leaderboard is unaffected.
              </p>
            </div>
            <pre className="code" style={{
              background: 'var(--canvas)', border: '1px solid var(--border)',
              borderRadius: 'var(--r-nested)', padding: 12, overflowX: 'auto',
              color: 'var(--error)', fontSize: 11,
            }}>
              {String(this.state.error?.message || this.state.error)}
            </pre>
            <div className="row gap-sm wrap">
              <button type="button" className="btn btn-primary btn-sm"
                onClick={() => this.setState({ error: null })}>
                Try this screen again
              </button>
              <Link to="/challenges" className="btn btn-secondary btn-sm"
                onClick={() => this.setState({ error: null })}>
                Back to challenges
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
