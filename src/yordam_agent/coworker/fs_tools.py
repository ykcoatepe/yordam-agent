import difflib
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional


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


def propose_write_file(path: Path, content: str, *, max_bytes: Optional[int] = None) -> str:
    existing = ""
    if path.exists():
        if max_bytes is None:
            existing = path.read_text(encoding="utf-8", errors="replace")
        elif max_bytes > 0:
            existing = read_text(path, max_bytes)
    diff = difflib.unified_diff(
        existing.splitlines(),
        content.splitlines(),
        fromfile=str(path),
        tofile=str(path),
        lineterm="",
    )
    return "\n".join(diff)


def apply_write_file(path: Path, content: str) -> None:
    write_path = path
    if path.is_symlink():
        try:
            write_path = path.resolve()
        except OSError:
            write_path = path
    write_path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = None
    if write_path.exists():
        try:
            existing_mode = write_path.stat().st_mode & 0o777
        except OSError:
            existing_mode = None
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(write_path.parent),
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(write_path)
    if existing_mode is not None:
        try:
            write_path.chmod(existing_mode)
        except OSError:
            pass
    else:
        try:
            current_umask = os.umask(0)
            os.umask(current_umask)
            write_path.chmod(0o666 & ~current_umask)
        except OSError:
            pass


def move_path(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def rename_path(src: Path, dst: Path) -> None:
    move_path(src, dst)
