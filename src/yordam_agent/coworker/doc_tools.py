import subprocess
from pathlib import Path
from typing import List


def extract_pdf_text(path: Path, max_chars: int, *, ocr_mode: str = "off") -> str:
    text = _spotlight_text(path, max_chars)
    if text or ocr_mode == "off":
        return text
    if ocr_mode == "ask":
        if not _prompt_for_ocr():
            return ""
    return _ocr_text(path, max_chars)


def extract_pdf_chunks(
    path: Path, max_chars: int, *, ocr_mode: str = "off", chunk_size: int = 3000
) -> List[str]:
    text = extract_pdf_text(path, max_chars, ocr_mode=ocr_mode)
    return chunk_text(text, chunk_size)


def chunk_text(text: str, size: int) -> List[str]:
    if size <= 0:
        return []
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _spotlight_text(path: Path, max_chars: int) -> str:
    try:
        result = subprocess.run(
            ["mdls", "-raw", "-name", "kMDItemTextContent", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    output = result.stdout.strip()
    if output in {"", "(null)"}:
        return ""
    return output[:max_chars]


def _ocr_text(path: Path, max_chars: int) -> str:
    try:
        result = subprocess.run(
            ["tesseract", str(path), "stdout"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()[:max_chars]


def _prompt_for_ocr() -> bool:
    script = (
        "set theButton to button returned of (display dialog "
        "\"Text could not be extracted. Use OCR? (slower)\" "
        "with title \"Yordam Agent\" "
        "buttons {\"Cancel\", \"Use OCR\"} "
        "default button \"Use OCR\" cancel button \"Cancel\")\n"
        "return theButton"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script], check=False, capture_output=True, text=True
        )
    except OSError:
        return False
    if result.returncode != 0:
        return False
    return result.stdout.strip() == "Use OCR"
