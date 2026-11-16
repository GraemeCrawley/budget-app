// The app's version is the moment it was built, shown in the phone's own time: "15 Nov, 18:12".
/* global __BUILT__ */
export const BUILT = typeof __BUILT__ === "undefined" ? null : __BUILT__;

export function versionWords(iso = BUILT) {
  const when = iso ? new Date(iso) : null;
  if (!when || Number.isNaN(when.getTime())) return "unknown";
  const day = when.toLocaleDateString("en-CA", { day: "numeric", month: "short" });
  const time = when.toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${day}, ${time}`;
}
