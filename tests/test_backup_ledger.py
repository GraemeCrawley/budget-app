"""Nightly ledger backup: a verified copy per day, old ones pruned, and nothing about the contents printed."""
import importlib.util
import sqlite3
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup-ledger.py"
_spec = importlib.util.spec_from_file_location("backup_ledger", SCRIPT)
bl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bl)


def _ledger(path, rows=3):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE t (x)")
    c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(rows)])
    c.commit(); c.close()


def test_a_backup_is_a_readable_copy_named_for_the_day(tmp_path):
    _ledger(tmp_path / "tracker.db")
    out = bl.backup(tmp_path / "tracker.db", tmp_path / "backups", date(2026, 1, 5))
    assert out == tmp_path / "backups" / "tracker-2026-01-05.db"
    c = sqlite3.connect(out)
    assert c.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3
    c.close()
    assert out.stat().st_mode & 0o077 == 0  # the owner alone can read it


def test_a_backup_taken_while_the_ledger_is_open_for_writing_is_still_whole(tmp_path):
    _ledger(tmp_path / "tracker.db")
    busy = sqlite3.connect(tmp_path / "tracker.db")
    busy.execute("INSERT INTO t VALUES (99)")  # an open, uncommitted write
    out = bl.backup(tmp_path / "tracker.db", tmp_path / "backups", date(2026, 1, 5))
    busy.rollback(); busy.close()
    c = sqlite3.connect(out)
    assert c.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3
    c.close()


def test_a_second_backup_on_the_same_day_replaces_the_first(tmp_path):
    _ledger(tmp_path / "tracker.db")
    bl.backup(tmp_path / "tracker.db", tmp_path / "backups", date(2026, 1, 5))
    c = sqlite3.connect(tmp_path / "tracker.db"); c.execute("INSERT INTO t VALUES (9)"); c.commit(); c.close()
    out = bl.backup(tmp_path / "tracker.db", tmp_path / "backups", date(2026, 1, 5))
    assert [p.name for p in (tmp_path / "backups").iterdir()] == ["tracker-2026-01-05.db"]
    c = sqlite3.connect(out)
    assert c.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 4
    c.close()


def test_only_the_newest_backups_are_kept_and_other_files_are_left_alone(tmp_path):
    _ledger(tmp_path / "tracker.db")
    dest = tmp_path / "backups"
    for day in range(1, 6):
        bl.backup(tmp_path / "tracker.db", dest, date(2026, 1, day), keep=3)
    (dest / "notes.txt").write_text("mine")
    bl.backup(tmp_path / "tracker.db", dest, date(2026, 1, 6), keep=3)
    assert sorted(p.name for p in dest.iterdir()) == [
        "notes.txt", "tracker-2026-01-04.db", "tracker-2026-01-05.db", "tracker-2026-01-06.db"]


def test_a_missing_ledger_fails_and_writes_nothing(tmp_path):
    with pytest.raises(bl.BackupFailed):
        bl.backup(tmp_path / "tracker.db", tmp_path / "backups", date(2026, 1, 5))
    assert not (tmp_path / "tracker.db").exists()  # opening it read-only must not create it
    assert not list((tmp_path / "backups").glob("*")) if (tmp_path / "backups").exists() else True


def test_a_damaged_ledger_fails_and_keeps_the_earlier_backups(tmp_path):
    _ledger(tmp_path / "tracker.db", rows=2000)
    dest = tmp_path / "backups"
    bl.backup(tmp_path / "tracker.db", dest, date(2026, 1, 5), keep=1)
    raw = bytearray((tmp_path / "tracker.db").read_bytes())
    raw[4096:8192] = b"\xff" * 4096  # wreck a page
    (tmp_path / "tracker.db").write_bytes(raw)
    with pytest.raises(bl.BackupFailed):
        bl.backup(tmp_path / "tracker.db", dest, date(2026, 1, 6), keep=1)
    assert [p.name for p in dest.iterdir()] == ["tracker-2026-01-05.db"]


def test_main_prints_counts_only_and_exits_zero(tmp_path, monkeypatch, capsys):
    _ledger(tmp_path / "tracker.db")
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert bl.main() == 0
    out = capsys.readouterr().out.strip()
    assert out == "ledger backup OK: 1 held"


def test_main_fails_nonzero_without_a_ledger(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert bl.main() == 1
    assert "ledger backup FAILED" in capsys.readouterr().err
