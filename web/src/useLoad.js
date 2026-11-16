// Load data for a screen: `{data, error, retry}`. While a load is out, data is null, so a screen
// never shows an old figure as current. Screens remount on navigation, so they refetch on show.
import { useCallback, useEffect, useState } from "react";

export default function useLoad(load, deps) {
  const [state, setState] = useState({ data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState({ data: null, error: null });
    load().then(
      (data) => live && setState({ data, error: null }),
      (error) => live && setState({ data: null, error }),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, retry };
}
