import pytest
from pathlib import Path
from connectors.registry import parse_file, UnrecognisedFile, all_connectors

FX = Path(__file__).parent.parent / "fixtures" / "connectors"

def test_parse_file_routes_to_the_connector():
    data = (FX / "ws_cash_monthly.csv").read_bytes()
    (b,) = parse_file("abc-Rainy_DaymonthlystatementtransactionsXX0000000CAD20260201.csv", data)
    assert b.connector == "wealthsimple_cash"

@pytest.mark.parametrize("data", [b"", b"\x00\x01\x02\xff\xfe", b"hello world\n"])
def test_unrecognised_files_raise_a_plain_error(data):
    with pytest.raises(UnrecognisedFile):
        parse_file("mystery.bin", data)

def test_every_connector_has_the_module_shape():
    for c in all_connectors():
        assert isinstance(c.NAME, str) and isinstance(c.VERSION, int)
        assert callable(c.sniff) and callable(c.parse)

def test_bad_amount_in_a_sniffed_file_raises_unrecognised():
    data = (b'"date","transaction","description","amount","balance","currency"\n'
            b'"2026-01-02","DEP","Invented","not-a-number","1.00","CAD"\n')
    with pytest.raises(UnrecognisedFile) as exc:
        parse_file("abc-Rainy_DaymonthlystatementtransactionsXX0000000CAD20260201.csv", data)
    assert "not-a-number" not in str(exc.value)

def test_filename_without_the_marker_raises_unrecognised():
    data = (FX / "ws_cash_monthly.csv").read_bytes()
    with pytest.raises(UnrecognisedFile):
        parse_file("export.csv", data)

def test_a_recognised_statement_that_fails_its_checks_is_refused_not_unrecognised():
    from connectors.registry import RefusedFile
    text = (FX / "cibc_statement.txt").read_text().replace("$2,420.00", "$2,421.00")
    with pytest.raises(RefusedFile) as exc:
        parse_file("x.txt", text.encode("utf-8"))
    assert isinstance(exc.value, UnrecognisedFile)  # callers that catch UnrecognisedFile still catch it
    with pytest.raises(UnrecognisedFile) as exc:
        parse_file("mystery.bin", b"hello world\n")
    assert not isinstance(exc.value, RefusedFile)

def test_only_a_connector_that_needs_an_account_is_given_one():
    from connectors import generic_csv
    assert generic_csv.NEEDS_ACCOUNT is True
    assert [c.NAME for c in all_connectors() if getattr(c, "NEEDS_ACCOUNT", False)] == ["generic_csv"]
    data = (FX / "cibc_statement.txt").read_bytes()
    (b,) = parse_file("x.txt", data, "some-card")
    assert b.account.key == "cibc-chequing"
    assert all(t.uid in {u.uid for u in parse_file("x.txt", data)[0].transactions} for t in b.transactions)

CASH_NAME = "abc-Rainy_DaymonthlystatementtransactionsXX0000000CAD20260201.csv"
CASH_HEADER = b'"date","transaction","description","amount","balance","currency"\n'

def test_a_file_with_no_transactions_is_unrecognised():
    with pytest.raises(UnrecognisedFile, match="no transactions in this file") as exc:
        parse_file(CASH_NAME, CASH_HEADER)
    from connectors.registry import RefusedFile
    assert not isinstance(exc.value, RefusedFile)


class _Stub:
    NAME, VERSION = "stub", 1
    def __init__(self, batches): self.batches = batches
    def sniff(self, filename, text): return True
    def parse(self, filename, text): return self.batches


def _empty(kind):
    from connectors.batch import AccountRef, StatementBatch, FORMAT_VERSION
    balances = (100, 100) if kind == "statement" else (None, None)
    return StatementBatch(FORMAT_VERSION, "stub", 1, AccountRef("k", "K", "chequing", "B"), kind,
                          "2026-01-01", "2026-01-31", *balances, ())


def test_a_statement_with_a_stated_period_and_no_transactions_is_kept(monkeypatch):
    import connectors.registry as registry
    monkeypatch.setattr(registry, "all_connectors", lambda: [_Stub([_empty("statement")])])
    assert len(parse_file("x.txt", b"anything")) == 1
    for batches in ([], [_empty("activity")]):
        monkeypatch.setattr(registry, "all_connectors", lambda: [_Stub(batches)])
        with pytest.raises(UnrecognisedFile, match="no transactions in this file"):
            parse_file("x.txt", b"anything")


@pytest.mark.parametrize("body", [
    b'"2026-01-02","DEP","Invented short row"\n',                    # a short row: AttributeError inside parse
    b'"2026-01-02","DEP","Invented ' + b"x" * 200_000 + b"\n",       # an unterminated quote: csv.Error
], ids=["short-row", "unterminated-quote"])
def test_any_parse_failure_is_unrecognised_with_a_fixed_reason(body):
    with pytest.raises(UnrecognisedFile) as exc:
        parse_file(CASH_NAME, CASH_HEADER + body)
    message = str(exc.value)
    assert "could not be read" in message
    for leak in ("Invented", "NoneType", "attribute", "field", "xxxx"):
        assert leak not in message


class _BadSniff:
    NAME, VERSION = "bad_sniff", 1
    def sniff(self, filename, text): raise RuntimeError("Invented secret")
    def parse(self, filename, text): raise AssertionError("never parsed")


def test_a_connector_whose_sniff_raises_does_not_claim_the_file(monkeypatch):
    import connectors.registry as registry
    monkeypatch.setattr(registry, "all_connectors", lambda: [_BadSniff(), _Stub([_empty("statement")])])
    assert len(parse_file("x.txt", b"anything")) == 1
    monkeypatch.setattr(registry, "all_connectors", lambda: [_BadSniff()])
    with pytest.raises(UnrecognisedFile, match="no known statement format") as exc:
        parse_file("x.txt", b"anything")
    assert "secret" not in str(exc.value)


# --- the failure codes an HTTP caller maps to fixed sentences ---

def _code_of(filename, data, *args):
    with pytest.raises(UnrecognisedFile) as exc:
        parse_file(filename, data, *args)
    return exc.value


def test_every_failure_carries_a_code():
    from connectors.registry import AccountNeeded, RefusedFile
    assert _code_of("mystery.bin", b"hello world\n").code == "no_format"
    assert _code_of(CASH_NAME, CASH_HEADER).code == "no_transactions"
    assert _code_of(CASH_NAME, CASH_HEADER + b'"2026-01-02","DEP","Invented short row"\n').code == "unreadable_row"
    assert _code_of(CASH_NAME, CASH_HEADER + b'"2026-01-02","DEP","Invented","not-a-number","1.00","CAD"\n'
                    ).code == "unreadable_row"
    needed = _code_of("export.csv", (FX / "activity_generic.csv").read_bytes())
    assert isinstance(needed, AccountNeeded) and needed.code == "account_needed"
    text = (FX / "cibc_statement.txt").read_text().replace("$2,420.00", "$2,421.00")
    refused = _code_of("x.txt", text.encode("utf-8"))
    assert isinstance(refused, RefusedFile)
    assert (refused.code, refused.problem_codes) == ("failed_checks", ["balance_mismatch"])


@pytest.mark.parametrize("boom", [ValueError("x"), RuntimeError("Invented secret"), OSError("y")])
def test_a_pdf_that_cannot_be_read_is_unreadable_pdf_whatever_went_wrong(monkeypatch, boom):
    import connectors.registry as registry
    def fail(data): raise boom
    monkeypatch.setattr(registry.pdftext, "to_text", fail)
    exc = _code_of("x.pdf", b"%PDF-1.4 invented")
    assert exc.code == "unreadable_pdf" and "secret" not in str(exc)
