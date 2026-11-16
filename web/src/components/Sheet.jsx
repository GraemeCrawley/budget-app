// A panel that slides up over the page, for choosing something. Escape or the backdrop closes it,
// and focus goes back to whatever opened it.
import { useEffect, useRef } from "react";

export default function Sheet({ title, onClose, children }) {
  const ref = useRef(null);
  const close = useRef(onClose);
  close.current = onClose; // a new function each render must not re-run the effect below
  useEffect(() => {
    const opener = document.activeElement;
    ref.current?.focus();
    const onKey = (e) => e.key === "Escape" && close.current();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);
  return (
    <div className="sheet-wrap">
      <div className="backdrop" onClick={onClose} aria-hidden="true" />
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <div className="row">
          <h2>{title}</h2>
          <button type="button" className="btn ghost close" onClick={onClose}>Close</button>
        </div>
        {children}
      </div>
    </div>
  );
}
