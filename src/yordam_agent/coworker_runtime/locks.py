import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


@dataclass
class LockHandle:
    paths: List[Path]
    lock_files: List[Path]

    def release(self) -> None:
        for lock_file in self.lock_files:
            try:
                lock_file.unlink()
            except FileNotFoundError:
                continue


def acquire_locks(
    paths: Iterable[Path],
    *,
    locks_dir: Path,
    task_id: str,
    owner: str,
) -> LockHandle:
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_files: List[Path] = []
    normalized = _normalize_paths(paths)
    for path in normalized:
        lock_file = locks_dir / _lock_name(path)
        if lock_file.exists():
            existing_task = _read_task_id(lock_file)
            if existing_task != task_id:
                _release_files(lock_files)
                return LockHandle(paths=[], lock_files=[])
        else:
            if not _create_lock(lock_file, task_id, owner):
                _release_files(lock_files)
                return LockHandle(paths=[], lock_files=[])
        lock_files.append(lock_file)
    return LockHandle(paths=normalized, lock_files=lock_files)


def release_task_locks(paths: Iterable[Path], *, locks_dir: Path, task_id: str) -> None:
    for path in _normalize_paths(paths):
        lock_file = locks_dir / _lock_name(path)
        if not lock_file.exists():
            continue
        if _read_task_id(lock_file) != task_id:
            continue
        try:
            lock_file.unlink()
        except FileNotFoundError:
            continue


def _normalize_paths(paths: Iterable[Path]) -> List[Path]:
    resolved = []
    for path in paths:
        resolved.append(Path(path).expanduser().resolve())
    return resolved


def _lock_name(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    safe = path.name.replace(" ", "_") or "root"
    return f"lock-{safe}-{digest}.lock"


def _create_lock(lock_file: Path, task_id: str, owner: str) -> bool:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(str(lock_file), flags)
    except FileExistsError:
        return False
    payload = _lock_payload(task_id, owner)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    return True


def _lock_payload(task_id: str, owner: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"task_id={task_id}\nowner={owner}\ncreated_at={ts}\n"


def _read_task_id(lock_file: Path) -> str:
    try:
        content = lock_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    for line in content.splitlines():
        if line.startswith("task_id="):
            return line.split("=", 1)[1].strip()
    return ""


def _release_files(lock_files: List[Path]) -> None:
    for lock_file in lock_files:
        try:
            lock_file.unlink()
        except FileNotFoundError:
            continue
