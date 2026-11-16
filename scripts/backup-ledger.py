#!/usr/bin/env python3
"""Nightly backup of the ledger: one verified copy per day in <data dir>/backups, the newest 30 kept.

Run by host cron. Uses SQLite's own backup, so a copy taken while the app is writing is still whole.
Prints a status and a count only: never anything from the ledger. Exits non-zero on any failure.

The copies sit on the same disk as the ledger: they guard against a bad change or a damaged file,
not against losing the machine.
"""
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

KEEP = 30
NAME = re.compile(r"^tracker-\d{4}-\d{2}-\d{2}\.db$")


class BackupFailed(Exception):
    pass


def backup(db_path: Path, dest: Path, day: date, keep: int = KEEP) -> Path:
    """Copy the ledger to dest/tracker-<day>.db, check the copy, then prune to the newest `keep`."""
    db_path, dest = Path(db_path), Path(dest)
    if not db_path.is_file():
        raise BackupFailed("no ledger")
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    out = dest / f"tracker-{day.isoformat()}.db"
    tmp = dest / f".{out.name}.partial"
    try:
        tmp.unlink(missing_ok=True)
        source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
        try:
            copy = sqlite3.connect(tmp)
            try:
                source.backup(copy)
                verdict = copy.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                copy.close()
        finally:
            source.close()
        if verdict != "ok":
            raise BackupFailed("the copy did not pass its check")
        os.chmod(tmp, 0o600)
        os.replace(tmp, out)
    except (sqlite3.Error, OSError) as exc:
        raise BackupFailed(type(exc).__name__) from None
    finally:
        tmp.unlink(missing_ok=True)
    held = sorted(p for p in dest.iterdir() if NAME.match(p.name))
    for old in held[:-keep]:
        old.unlink()
    return out


def main() -> int:
    data_dir = Path(os.environ.get("GB_DATA_DIR") or Path(__file__).resolve().parent.parent / "private")
    dest = data_dir / "backups"
    try:
        backup(data_dir / "tracker.db", dest, date.today())
    except BackupFailed as exc:
        print(f"ledger backup FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"ledger backup OK: {sum(1 for p in dest.iterdir() if NAME.match(p.name))} held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
