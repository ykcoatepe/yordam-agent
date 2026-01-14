import json
import os
import re
from pathlib import Path
from typing import Optional

TEXT_EXTS = {
    ".txt",
    ".md",
    ".markdown",
    ".rtf",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".css",
    ".sql",
    ".swift",
    ".java",
    ".go",
    ".rs",
    ".sh",
    ".zsh",
    ".bash",
}


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def sanitize_folder_name(name: str) -> str:
    cleaned = re.sub(r"[\\/]+", "-", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"[^A-Za-z0-9 _\-]", "", cleaned)
    if not cleaned or cleaned in {".", ".."}:
        return "Unsorted"
    if len(cleaned) > 40:
        cleaned = cleaned[:40].rstrip()
    return cleaned


def extract_json_object(text: str) -> Optional[dict]:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def read_text_snippet(path: Path, max_chars: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(max_chars)
    except OSError:
        return ""


def file_extension(path: Path) -> str:
    return path.suffix.lower()


def is_text_extension(ext: str) -> bool:
    return ext in TEXT_EXTS


def ensure_dir(path: Path) -> None:
    os.makedirs(path, exist_ok=True)
