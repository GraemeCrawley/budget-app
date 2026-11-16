// Press or drag across a chart to read one month's values. The chart keeps scrolling up and down
// under a finger; only sideways movement is ours. The reading stays after the finger lifts and
// goes when something else is pressed.
import { useEffect, useRef, useState } from "react";

const REST = 120; // milliseconds a finger rests on a chart before the touch is ours whichever way it moves
const DRAG = 6; // pixels of sideways travel before a press counts as a drag, not a tap

// count: how many months are drawn across the plot area. A line chart spaces them from edge to edge;
// a bar chart (bands) gives each an equal slice.
export function useScrub(count, bands = false) {
  const [at, setAt] = useState(null);
  const wrap = useRef(null);
  const plot = useRef(null);
  const press = useRef(null); // where the press began, and whether it became a drag

  useEffect(() => {
    if (at == null) return undefined;
    const away = (e) => { if (!wrap.current?.contains(e.target)) setAt(null); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [at]);

  // A touch on a chart is ours, and the screen must not scroll under it, in two cases: the finger
  // set off sideways, or it rested on the chart for a moment before moving (pressing to read, then
  // sliding). Only a quick flick up or down is left alone, and scrolls. A phone lets a gesture be
  // claimed only before it starts scrolling, so a rested finger is claimed before it moves at all;
  // and while the gesture is ours the scrolling screen is held still as well.
  useEffect(() => {
    const el = wrap.current;
    if (!el) return undefined;
    let from = null;
    let ours = false;
    let held = null; // the scrolling screen, while we hold it
    let rest = null; // the timer for a finger resting on the chart
    const release = () => {
      clearTimeout(rest);
      if (held) held.style.overflowY = "";
      held = null;
      from = null;
      ours = false;
    };
    const claim = () => {
      clearTimeout(rest);
      ours = true;
      held = el.closest("#root");
      if (held) held.style.overflowY = "hidden";
    };
    const down = (e) => {
      release();
      from = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      rest = setTimeout(claim, REST);
    };
    const move = (e) => {
      if (!from) return;
      if (!ours) {
        const dx = Math.abs(e.touches[0].clientX - from.x);
        const dy = Math.abs(e.touches[0].clientY - from.y);
        if (dy > dx) { clearTimeout(rest); from = null; return; }
        claim();
      }
      if (e.cancelable) e.preventDefault();
    };
    el.addEventListener("touchstart", down, { passive: true });
    el.addEventListener("touchmove", move, { passive: false });
    el.addEventListener("touchend", release);
    el.addEventListener("touchcancel", release);
    return () => {
      release();
      el.removeEventListener("touchstart", down);
      el.removeEventListener("touchmove", move);
      el.removeEventListener("touchend", release);
      el.removeEventListener("touchcancel", release);
    };
  }, []);

  const nearest = (x) => {
    const box = plot.current?.getBoundingClientRect();
    if (!box || box.width <= 0 || count < 1) return null;
    if (count === 1) return 0;
    const t = (x - box.left) / box.width;
    const i = bands ? Math.floor(t * count) : Math.round(t * (count - 1));
    return Math.max(0, Math.min(count - 1, i));
  };

  const handlers = {
    onPointerDown: (e) => { press.current = { x: e.clientX, dragged: false }; setAt(nearest(e.clientX)); },
    onPointerMove: (e) => {
      if (press.current && Math.abs(e.clientX - press.current.x) > DRAG) press.current.dragged = true;
      if (press.current || e.pointerType === "mouse") setAt(nearest(e.clientX));
    },
    onPointerUp: () => { if (press.current && !press.current.dragged) press.current = null; },
    onPointerCancel: () => { press.current = null; },
    onPointerLeave: (e) => { if (e.pointerType === "mouse") { press.current = null; setAt(null); } },
    // the end of a drag must not open the month it ended on
    onClickCapture: (e) => {
      if (press.current?.dragged) { e.preventDefault(); e.stopPropagation(); }
      press.current = null;
    },
  };
  return { at, wrap, plot, handlers };
}

// The guide line and the reading, drawn over the plot area. A chart that shows its reading
// elsewhere (in a key above it) passes no children and gets the guide line alone. left and right match the chart's axis
// width and right margin.
export function Reading({ scrub, count, left, right, bands = false, children }) {
  const { at, plot } = scrub;
  const t = at == null ? 0 : bands ? (at + 0.5) / count : count < 2 ? 0 : at / (count - 1);
  return (
    <div className="plot" ref={plot} style={{ left, right }}>
      {at != null && (
        <>
          <i className="guide" style={{ left: `${t * 100}%` }} />
          {children && (
            <p className="tip" role="status" style={{ left: `${t * 100}%`, transform: `translate(${-t * 100}%, -100%)` }}>
              {children}
            </p>
          )}
        </>
      )}
    </div>
  );
}
