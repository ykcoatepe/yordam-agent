import difflib
import shutil
from pathlib import Path
from typing import List


def read_text(path: Path, max_bytes: int) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return fh.read(max_bytes)


def list_dir(path: Path, max_entries: int = 200) -> List[str]:
    entries = []
    for entry in sorted(path.iterdir()):
        entries.append(entry.name)
        if len(entries) >= max_entries:
            break
    return entries


def propose_write_file(path: Path, content: str) -> str:
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="replace")
    diff = difflib.unified_diff(
        existing.splitlines(),
        content.splitlines(),
        fromfile=str(path),
        tofile=str(path),
        lineterm="",
    )
    return "\n".join(diff)


def apply_write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def move_path(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def rename_path(src: Path, dst: Path) -> None:
    move_path(src, dst)
