"""PDF to layout text, via poppler's pdftotext."""
import subprocess


def is_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF")


def to_text(data: bytes) -> str:
    try:
        result = subprocess.run(["pdftotext", "-layout", "-", "-"], input=data,
                                capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        raise ValueError("could not read this PDF") from None
    if result.returncode != 0:
        raise ValueError("could not read this PDF")
    return result.stdout.decode("utf-8", errors="replace")
