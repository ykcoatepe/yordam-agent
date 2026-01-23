import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


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
    normalized = _dedupe_paths(_normalize_paths(paths))
    existing_locks = _load_existing_locks(locks_dir)
    for path in normalized:
        if _has_overlap_conflict(path, existing_locks, locks_dir, task_id):
            _release_files(lock_files)
            return LockHandle(paths=[], lock_files=[])
        lock_file = locks_dir / _lock_name(path)
        if lock_file.exists():
            existing_task = _read_task_id(lock_file)
            if existing_task != task_id:
                _release_files(lock_files)
                return LockHandle(paths=[], lock_files=[])
        else:
            if not _create_lock(lock_file, task_id, owner, path):
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
    seen = set()
    for path in paths:
        resolved_path = Path(path).expanduser().resolve()
        if resolved_path in seen:
            continue
        seen.add(resolved_path)
        resolved.append(resolved_path)
    return resolved


def _dedupe_paths(paths: List[Path]) -> List[Path]:
    ordered = sorted(paths, key=lambda item: len(item.parts))
    deduped: List[Path] = []
    for path in ordered:
        if any(_is_within(path, root) for root in deduped):
            continue
        deduped.append(path)
    return deduped


def _is_within(path: Path, root: Path) -> bool:
    if path == root:
        return True
    try:
        return path.is_relative_to(root)
    except AttributeError:
        return str(path).startswith(f"{root}{os.sep}")


def _lock_name(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    safe = path.name.replace(" ", "_") or "root"
    return f"lock-{safe}-{digest}.lock"


def _create_lock(lock_file: Path, task_id: str, owner: str, path: Path) -> bool:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(str(lock_file), flags)
    except FileExistsError:
        return False
    payload = _lock_payload(task_id, owner, path)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    return True


def _lock_payload(task_id: str, owner: str, path: Path) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"path={path}\ntask_id={task_id}\nowner={owner}\ncreated_at={ts}\n"


def _read_task_id(lock_file: Path) -> str:
    try:
        content = lock_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    for line in content.splitlines():
        if line.startswith("task_id="):
            return line.split("=", 1)[1].strip()
    return ""


def _read_lock_path(lock_file: Path) -> Optional[Path]:
    try:
        content = lock_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    for line in content.splitlines():
        if line.startswith("path="):
            raw = line.split("=", 1)[1].strip()
            if not raw:
                return None
            try:
                return Path(raw).expanduser().resolve()
            except OSError:
                return None
    return None


def _load_existing_locks(locks_dir: Path) -> List[Tuple[Optional[Path], str]]:
    if not locks_dir.exists():
        return []
    entries: List[Tuple[Optional[Path], str]] = []
    for lock_file in locks_dir.glob("lock-*.lock"):
        task_id = _read_task_id(lock_file)
        lock_path = _read_lock_path(lock_file)
        entries.append((lock_path, task_id))
    return entries


def _has_overlap_conflict(
    path: Path,
    existing_locks: List[Tuple[Optional[Path], str]],
    locks_dir: Path,
    task_id: str,
) -> bool:
    for root in [path, *path.parents]:
        lock_file = locks_dir / _lock_name(root)
        if not lock_file.exists():
            continue
        existing_task = _read_task_id(lock_file)
        if existing_task and existing_task != task_id:
            return True
    for lock_path, existing_task in existing_locks:
        if not existing_task or existing_task == task_id:
            continue
        if lock_path is None:
            continue
        if _is_within(lock_path, path) or _is_within(path, lock_path):
            return True
    return False


def _release_files(lock_files: List[Path]) -> None:
    for lock_file in lock_files:
        try:
            lock_file.unlink()
        except FileNotFoundError:
            continue
