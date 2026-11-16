"""Finds the connector for a file and returns checked statement batches."""
from connectors import (amex, cibc_chequing, generic_csv, pdftext, wealthsimple_bills, wealthsimple_card,
                        wealthsimple_cash)
from connectors.batch import StatementBatch
from connectors.contract import check_batch, check_batch_codes
from connectors.parsing import NotTaken, ReadableError, decode


class UnrecognisedFile(Exception):
    """The file cannot be turned into batches. The message is for local eyes (it can quote the file);
    `code` is the fixed, file-free reason a caller may pass on: no_format, unreadable_pdf, unreadable_row,
    no_transactions, account_needed, not_taken or failed_checks."""

    code = "no_format"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code


class AccountNeeded(UnrecognisedFile):
    """The file is one whose account the caller must name (key and kind), and it was not named."""

    code = "account_needed"


class RefusedFile(UnrecognisedFile):
    """A connector read the file, but the batch failed its checks (for example it does not balance)."""

    code = "failed_checks"

    def __init__(self, message: str, problem_codes: list[str] | None = None):
        super().__init__(message)
        self.problem_codes = list(problem_codes or [])


def all_connectors() -> list:
    return [wealthsimple_cash, wealthsimple_card, cibc_chequing, amex, wealthsimple_bills, generic_csv]


def _claims(connector, filename: str, text: str) -> bool:
    """Whether the connector claims the file; a sniff that raises does not claim it."""
    try:
        return bool(connector.sniff(filename, text))
    except Exception:
        return False


def parse_file(filename: str, data: bytes, account_key: str | None = None,
               account_kind: str | None = None) -> list[StatementBatch]:
    if pdftext.is_pdf(data):
        try:
            text = pdftext.to_text(data)
        except Exception:  # whatever went wrong, the reason is the same fixed one
            raise UnrecognisedFile(f"{filename}: could not read this PDF", "unreadable_pdf") from None
    else:
        text = decode(data)
    for connector in all_connectors():
        if _claims(connector, filename, text):
            needs_account = getattr(connector, "NEEDS_ACCOUNT", False)
            try:
                if needs_account:
                    batches = connector.parse(filename, text, account_key, account_kind)
                else:  # a connector that identifies its own account is never given the caller's
                    batches = connector.parse(filename, text)
            except NotTaken:
                raise UnrecognisedFile(f"{filename}: {connector.NAME} does not take this kind of account",
                                       "not_taken") from None
            except ReadableError as e:
                if needs_account and (account_key is None or account_kind is None):
                    raise AccountNeeded(f"{filename}: {e}") from None
                raise UnrecognisedFile(f"{filename}: {e}", "unreadable_row") from None
            except Exception:  # any other failure: a fixed reason, never the exception's text (it can quote the file)
                raise UnrecognisedFile(
                    f"{filename}: looks like {connector.NAME} but a row or the file name could not be read",
                    "unreadable_row") from None
            # an activity's period is only the span of its rows, so without rows it states no period
            if not batches or any(not b.transactions and (b.kind == "activity" or not b.period_start)
                                  for b in batches):
                raise UnrecognisedFile(f"{filename}: no transactions in this file", "no_transactions")
            for batch in batches:
                problems = check_batch(batch)
                if problems:
                    raise RefusedFile(
                        f"{filename}: read as {connector.NAME} but it failed checks: " + "; ".join(problems),
                        check_batch_codes(batch))
            return batches
    raise UnrecognisedFile(f"{filename}: no known statement format matches this file")
