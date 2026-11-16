// A failed request, said plainly, with a way to try again. `message` defaults to the load wording;
// a save passes "Couldn't save that. Try again." The server's own detail (e.g. "not signed in") is
// shown beneath when there is one. A 401 means the sign-in has expired. A request that never got an
// answer (status 0) is either a dropped connection or the login redirect failing the request, and the
// two cannot be told apart, so it says both. Either way the only offer is to load the page again,
// which signs in again if that is what was needed.
import { reloadPage } from "../reload.js";

export function signInExpired(error) {
  return Boolean(error) && (error.status === 0 || error.status === 401);
}

export default function Problem({ error, onRetry, retryLabel = "Retry", message = "Couldn't load this. Try again." }) {
  if (signInExpired(error)) {
    return (
      <div className="panel problem" role="alert">
        <p>{error.status === 0 ? "Couldn't reach the app. Your sign-in may have expired." : "Your sign-in has expired."}</p>
        <button type="button" className="btn ghost" onClick={() => reloadPage()}>
          {error.status === 0 ? "Reload" : "Sign in again"}
        </button>
      </div>
    );
  }
  const detail = error && error.status > 0 && error.detail ? error.detail : null;
  return (
    <div className="panel problem" role="alert">
      <p>{message}</p>
      {detail && <p className="small muted">The server said: {detail}</p>}
      {onRetry && (
        <button type="button" className="btn ghost" onClick={onRetry}>
          {retryLabel}
        </button>
      )}
    </div>
  );
}
