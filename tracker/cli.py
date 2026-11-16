"""Command line for the ledger: ingest statement files, seed rules, check months.

Output holds file names, statuses and counts only: never amounts, descriptions or file contents.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from connectors.contract import ACCOUNT_KINDS
from connectors.registry import AccountNeeded, RefusedFile, UnrecognisedFile, parse_file
from tracker import push
from tracker.merchant import PREVIOUS_KEYS, merchant_key
from tracker.months import month_facts
from tracker.rules import OWNER_CARRIED, OWNER_FIRST, load_rules, seed_rules, set_merchant_rule
from tracker.store import accept_batch, as_held_cash_kind, held_account_kind, open_db, write_tx

USER_ID = 1
# Owner rules run after the seed's kind rules (transfers, rent, pay, travel) and before its category rules.
OWNER_PRIORITY = OWNER_CARRIED


def _signs_flipped(conn, batch) -> bool:
    """An activity export for a held card account whose signs the app flips (accounts.flip_sign)."""
    if batch.kind != "activity" or batch.account.kind != "card":
        return False
    row = conn.execute("SELECT flip_sign FROM accounts WHERE user_id = ? AND key = ? AND kind = 'card'",
                       (USER_ID, batch.account.key)).fetchone()
    return bool(row and row["flip_sign"])


def _ingest(conn, files: list[str], account_key, new_account_kind) -> int:
    """Read each file into the ledger. --account names the account for a file that does not name its own;
    a key the ledger holds keeps its stored kind, and a new key needs --new-account KIND."""
    failed = False
    account_kind = None
    if account_key is not None:
        account_kind = held_account_kind(conn, USER_ID, account_key) or new_account_kind
    for path in files:
        name = Path(path).name
        try:
            data = Path(path).read_bytes()
        except OSError:
            print(f"{name}: could not be read")
            failed = True
            continue
        try:
            batches = parse_file(name, data, account_key, account_kind)
        except AccountNeeded:
            if account_key is None:
                print(f"{name}: unrecognised")
            else:
                print(f"{name}: refused: the ledger holds no account {account_key};"
                      f" add --new-account KIND to create it")
            failed = True
            continue
        except RefusedFile:
            print(f"{name}: refused")
            failed = True
            continue
        except UnrecognisedFile:
            print(f"{name}: unrecognised")
            failed = True
            continue
        batches = [as_held_cash_kind(conn, USER_ID, batch) for batch in batches]
        if any(_signs_flipped(conn, batch) for batch in batches):
            # the app flips this card's exports as it takes them; storing them unflipped here would be wrong
            print(f"{name}: refused: this card's exports are stored with their signs flipped;"
                  f" upload this file through the app")
            failed = True
            continue
        for batch in batches:
            r = accept_batch(conn, USER_ID, batch, data, name)
            print(f"{name}: {r.status} added={r.added} already_held={r.already_held}"
                  f" confirmed={r.confirmed} differences={len(r.differences)}")
            failed = failed or r.status == "refused"
    return 1 if failed else 0


def _seed(conn, rules_file: str) -> int:
    try:
        text = Path(rules_file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        print(f"seed failed, rules unchanged: {Path(rules_file).name} could not be read", file=sys.stderr)
        return 1
    try:
        n = seed_rules(conn, USER_ID, json.loads(text))
    except (TypeError, ValueError) as exc:
        reason = re.sub(r"invalid pattern .*", "invalid pattern", str(exc))  # the pattern itself is the owner's data
        print(f"seed failed, rules unchanged: {reason}", file=sys.stderr)
        return 1
    print(f"seeded {n} rules")
    return 0


def _owner_rules(conn, merchants_file: str, priority: int) -> int:
    """One owner rule per confirmed merchant key: money out from that merchant.

    Safe to re-run: a held merchant is left alone, or its category updated if the file now says otherwise.
    Only this command's own rules are held (money out, at `priority`); the app's priority is refused.
    """
    if priority == OWNER_FIRST:
        print(f"owner-rules cannot write at priority {OWNER_FIRST}, the app's own; nothing written", file=sys.stderr)
        return 1
    try:
        text = Path(merchants_file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        print(f"owner-rules failed, nothing written: {Path(merchants_file).name} could not be read", file=sys.stderr)
        return 1
    try:
        merchants = json.loads(text)
    except ValueError:
        merchants = None
    if not isinstance(merchants, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in merchants.items()):
        print("owner-rules needs a JSON object mapping merchant text to a category; nothing written",
              file=sys.stderr)
        return 1
    with write_tx(conn):
        # the old anchored form (a prefix pattern, no merchant key) is replaced by merchant-key rules
        conn.execute("DELETE FROM rules WHERE user_id = ? AND origin = 'owner' AND merchant_key IS NULL"
                     " AND pattern LIKE '^\\s*%'", (USER_ID,))
        # only this command's own rules (money out, carried priority): never an in-app or a money-in rule
        held = {r.merchant_key: r for r in load_rules(conn, USER_ID) if r.origin == "owner" and r.merchant_key
                and r.sign == -1 and r.priority == priority}
        added = present = updated = skipped = 0
        for merchant, category in merchants.items():
            key = merchant.strip().upper()
            if not key:
                skipped += 1
                continue
            rule = held.get(key)
            if rule is None:
                set_merchant_rule(conn, USER_ID, key, -1, "spending", category, priority=priority)
                added += 1
            elif rule.category != category:
                set_merchant_rule(conn, USER_ID, key, -1, "spending", category, priority=priority)
                updated += 1
            else:
                present += 1
    print(f"added {added} owner rules, {present} already present, {updated} updated, {skipped} skipped")
    return 0


def _rekey(conn) -> int:
    """Move owner rules keyed by an earlier merchant-key algorithm to the current one. Prints counts only.

    A rule moves when every charge of the user (superseded ones too) that an earlier algorithm keyed to the rule's
    key now has the same one new key. Safe to run twice: a moved rule then matches its own new key. Two rules
    that land on one key are merged when they say the same thing, and left alone (a conflict) when they differ.
    """
    moved = unchanged = no_charges = ambiguous = conflicts = merged = 0
    with write_tx(conn):
        old_to_new: dict[str, set[str]] = {}
        for r in conn.execute("SELECT description FROM transactions WHERE user_id = ?", (USER_ID,)):
            for previous in PREVIOUS_KEYS:
                old_to_new.setdefault(previous(r["description"]), set()).add(merchant_key(r["description"]))
        rules = conn.execute("SELECT id, sign, priority, merchant_key, label, kind, category FROM rules"
                             " WHERE user_id = ? AND merchant_key IS NOT NULL ORDER BY id", (USER_ID,)).fetchall()
        for rule in rules:
            news = old_to_new.get(rule["merchant_key"], set())
            if not news:
                no_charges += 1
            elif len(news) > 1:
                ambiguous += 1
            else:
                (new,) = news
                if new == rule["merchant_key"]:
                    unchanged += 1
                elif held := conn.execute("SELECT kind, category FROM rules WHERE user_id = ? AND merchant_key = ?"
                                          " AND sign IS ? AND priority = ? AND id <> ?",
                                          (USER_ID, new, rule["sign"], rule["priority"], rule["id"])).fetchone():
                    if (held["kind"], held["category"]) == (rule["kind"], rule["category"]):
                        conn.execute("DELETE FROM rules WHERE id = ? AND user_id = ?", (rule["id"], USER_ID))
                        merged += 1
                    else:
                        conflicts += 1
                else:
                    label = f"you said {new}" if rule["label"] == f"you said {rule['merchant_key']}" else rule["label"]
                    conn.execute("UPDATE rules SET merchant_key = ?, label = ? WHERE id = ? AND user_id = ?",
                                 (new, label, rule["id"], USER_ID))
                    moved += 1
    print(f"rekeyed {moved}, merged {merged}, unchanged {unchanged}, no charges {no_charges},"
          f" ambiguous {ambiguous}, conflicts {conflicts}")
    return 0


def _check(conn) -> int:
    for m in month_facts(conn, USER_ID):
        print(f"{m.month} complete={'yes' if m.complete else 'no'}"
              f" provisional={'yes' if m.provisional else 'no'} uncategorised={m.uncategorised_count}"
              f" unconfirmed_income={m.unconfirmed_income_count}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m tracker.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="read statement files into the ledger")
    ingest.add_argument("files", nargs="+")
    ingest.add_argument("--account", metavar="KEY", help="account key for files that do not name one")
    ingest.add_argument("--new-account", metavar="KIND", choices=ACCOUNT_KINDS,
                        help="create the --account key as a new account of this kind: " + ", ".join(ACCOUNT_KINDS))
    seed = commands.add_parser("seed", help="replace the seed rules with those in a JSON file")
    seed.add_argument("rules_file")
    owner = commands.add_parser("owner-rules", help="add owner rules from a JSON object of merchant -> category")
    owner.add_argument("merchants_file")
    owner.add_argument("--priority", type=int, default=OWNER_PRIORITY)
    commands.add_parser("rekey", help="re-key stored owner rules after a change to the merchant key")
    commands.add_parser("check", help="print each month's completeness")
    commands.add_parser("remind", help="send the monthly reminder to the owner's phone if any account lacks last month")
    args = parser.parse_args(argv)

    data_dir = os.environ.get("GB_DATA_DIR")
    if not data_dir or not os.path.isdir(data_dir):
        print("GB_DATA_DIR must be set to an existing data directory", file=sys.stderr)
        return 2
    conn = open_db(os.path.join(data_dir, "tracker.db"))
    try:
        if args.command == "ingest":
            return _ingest(conn, args.files, args.account, args.new_account)
        if args.command == "seed":
            return _seed(conn, args.rules_file)
        if args.command == "owner-rules":
            return _owner_rules(conn, args.merchants_file, args.priority)
        if args.command == "rekey":
            return _rekey(conn)
        if args.command == "remind":
            code, line = push.remind(conn, data_dir, USER_ID)
            print(line)
            return code
        return _check(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
