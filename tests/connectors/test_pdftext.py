import shutil
import pytest

from connectors import registry
from connectors.pdftext import is_pdf, to_text


def test_is_pdf():
    assert is_pdf(b"%PDF-1.7\n...") and not is_pdf(b"date,amount\n")


def test_unreadable_pdf_raises_value_error():
    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext not installed on this machine")
    with pytest.raises(ValueError):
        to_text(b"%PDF-1.7\nthis is not really a pdf")


def test_missing_binary_raises_value_error(monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(ValueError, match="could not read this PDF"):
        to_text(b"%PDF-1.7\n")


def test_unreadable_pdf_is_unrecognised_via_registry():
    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext not installed on this machine")
    with pytest.raises(registry.UnrecognisedFile):
        registry.parse_file("x.pdf", b"%PDF-1.7\nthis is not really a pdf")
