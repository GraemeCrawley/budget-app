// The last line of defence: anything that throws while rendering shows the plain problem text and a
// reload button, never a blank page.
import { Component } from "react";

export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    const reload = this.props.onReload ?? (() => window.location.reload());
    return (
      <main className="app">
        <div className="panel problem" role="alert">
          <p>Couldn't load this. Try again.</p>
          <button type="button" className="btn ghost" onClick={reload}>
            Reload
          </button>
        </div>
      </main>
    );
  }
}
