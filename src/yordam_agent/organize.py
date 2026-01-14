import fnmatch
import json
import mimetypes
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .ollama import OllamaClient
from .util import (
    ensure_dir,
    extract_json_object,
    file_extension,
    is_hidden,
    is_text_extension,
    read_text_snippet,
    sanitize_folder_name,
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".tiff", ".bmp", ".heic", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg"}
ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tgz", ".rar", ".7z"}
DOC_EXTS = {".pdf", ".doc", ".docx", ".pages"}
PRESENTATION_EXTS = {".ppt", ".pptx", ".key"}
SPREADSHEET_EXTS = {".xls", ".xlsx", ".numbers"}
CODE_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".swift",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".html",
    ".css",
}
DATA_EXTS = {".csv", ".tsv", ".json", ".parquet"}

DEFAULT_CATEGORIES = [
    "Documents",
    "Media",
    "Images",
    "Video",
    "Audio",
    "Code",
    "Data",
    "Design",
    "Projects",
    "Work",
    "Personal",
    "Finance",
    "Legal",
    "Notes",
    "Presentations",
    "Spreadsheets",
    "Archives",
    "Installers",
]


@dataclass
class FileMeta:
    path: Path
    name: str
    extension: str
    size_bytes: int
    modified_iso: str
    type_group: str
    snippet: str


@dataclass
class MoveOp:
    src: Path
    dst: Path
    category: str
    subcategory: Optional[str]


def _type_group_for(ext: str, mime: Optional[str]) -> str:
    if ext in IMAGE_EXTS:
        return "Image"
    if ext in VIDEO_EXTS:
        return "Video"
    if ext in AUDIO_EXTS:
        return "Audio"
    if ext in ARCHIVE_EXTS:
        return "Archive"
    if ext in DOC_EXTS:
        return "Document"
    if ext in PRESENTATION_EXTS:
        return "Presentation"
    if ext in SPREADSHEET_EXTS:
        return "Spreadsheet"
    if ext in CODE_EXTS:
        return "Code"
    if ext in DATA_EXTS:
        return "Data"
    if mime and mime.startswith("image/"):
        return "Image"
    if mime and mime.startswith("video/"):
        return "Video"
    if mime and mime.startswith("audio/"):
        return "Audio"
    if mime and mime.startswith("text/"):
        return "Text"
    return "Other"


def _spotlight_snippet(path: Path, max_chars: int) -> str:
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
    if output in {"(null)", ""}:
        return ""
    return output[:max_chars]


def build_file_meta(path: Path, max_snippet_chars: int) -> FileMeta:
    stat = path.stat()
    ext = file_extension(path)
    mime, _ = mimetypes.guess_type(str(path))
    group = _type_group_for(ext, mime)
    snippet = ""
    if is_text_extension(ext):
        snippet = read_text_snippet(path, max_snippet_chars)
    else:
        snippet = _spotlight_snippet(path, max_snippet_chars)
    modified_iso = datetime.fromtimestamp(stat.st_mtime).isoformat()
    return FileMeta(
        path=path,
        name=path.name,
        extension=ext,
        size_bytes=stat.st_size,
        modified_iso=modified_iso,
        type_group=group,
        snippet=snippet,
    )


def gather_files(
    root: Path, recursive: bool, include_hidden: bool, ignore_patterns: List[str]
) -> List[Path]:
    files: List[Path] = []
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            for dirname in list(dirnames):
                rel_dir = (Path(dirpath) / dirname).relative_to(root)
                if not include_hidden and dirname.startswith("."):
                    dirnames.remove(dirname)
                    continue
                if ".yordam-agent" in rel_dir.parts:
                    dirnames.remove(dirname)
                    continue
                if _is_ignored(rel_dir, ignore_patterns):
                    dirnames.remove(dirname)
                    continue
            for fname in filenames:
                path = Path(dirpath) / fname
                if path.is_symlink() or not path.is_file():
                    continue
                if not include_hidden and is_hidden(path.relative_to(root)):
                    continue
                if ".yordam-agent" in path.parts:
                    continue
                if _is_ignored(path.relative_to(root), ignore_patterns):
                    continue
                files.append(path)
    else:
        for path in root.iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            if not include_hidden and path.name.startswith("."):
                continue
            if path.name == ".yordam-agent":
                continue
            if _is_ignored(path.relative_to(root), ignore_patterns):
                continue
            files.append(path)
    return files


def _normalize_override(value: object) -> Optional[Tuple[str, Optional[str]]]:
    if isinstance(value, str) and value.strip():
        return value.strip(), None
    if isinstance(value, dict):
        category = str(value.get("category", "")).strip()
        subcategory = value.get("subcategory")
        if isinstance(subcategory, str):
            subcategory = subcategory.strip()
        else:
            subcategory = None
        if category:
            return category, subcategory
    return None


def _is_ignored(path: Path, patterns: List[str]) -> bool:
    if not patterns:
        return False
    rel_str = str(path)
    for pattern in patterns:
        if not pattern:
            continue
        if fnmatch.fnmatch(rel_str, pattern) or fnmatch.fnmatch(path.name, pattern):
            return True
        for part in path.parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def apply_policy(meta: FileMeta, policy: Dict[str, object]) -> Optional[Tuple[str, Optional[str]]]:
    ext_overrides = policy.get("extension_overrides", {})
    if isinstance(ext_overrides, dict):
        override = _normalize_override(ext_overrides.get(meta.extension))
        if override:
            return override

    type_overrides = policy.get("type_group_overrides", {})
    if isinstance(type_overrides, dict):
        override = _normalize_override(type_overrides.get(meta.type_group))
        if override:
            return override

    name_rules = policy.get("name_contains_rules", [])
    if isinstance(name_rules, list):
        lowered = meta.name.lower()
        for rule in name_rules:
            if not isinstance(rule, dict):
                continue
            needle = str(rule.get("contains", "")).lower().strip()
            if needle and needle in lowered:
                override = _normalize_override(rule)
                if override:
                    return override
    return None


def _fallback_category(group: str) -> Tuple[str, Optional[str]]:
    if group == "Image":
        return "Images", None
    if group == "Video":
        return "Video", None
    if group == "Audio":
        return "Audio", None
    if group == "Archive":
        return "Archives", None
    if group == "Presentation":
        return "Presentations", None
    if group == "Spreadsheet":
        return "Spreadsheets", None
    if group == "Code":
        return "Code", None
    if group == "Data":
        return "Data", None
    if group in {"Document", "Text"}:
        return "Documents", None
    return "Documents", None


def classify_file(
    meta: FileMeta,
    client: OllamaClient,
    model: str,
    policy: Dict[str, object],
    context: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    override = apply_policy(meta, policy)
    if override:
        return override
    system = (
        "You are a careful file organization assistant. "
        "Choose a stable category and optional subcategory for a file. "
        "Use short Title Case names without slashes. "
        "Prefer reusable categories."
    )
    context_line = f"User context: {context}\n" if context else ""
    prompt = (
        "Given this file metadata, choose a category and optional subcategory.\n"
        f"File name: {meta.name}\n"
        f"Extension: {meta.extension or 'none'}\n"
        f"Type group: {meta.type_group}\n"
        f"Size bytes: {meta.size_bytes}\n"
        f"Modified: {meta.modified_iso}\n"
        f"Snippet: {meta.snippet[:800]}\n"
        f"{context_line}\n"
        "Available category examples: "
        + ", ".join(DEFAULT_CATEGORIES)
        + "\n\n"
        "Return ONLY JSON: {\"category\": \"...\", \"subcategory\": \"...\"}. "
        "If subcategory is not needed, use null."
    )
    raw = client.generate(
        model=model,
        prompt=prompt,
        system=system,
        temperature=0.2,
        log_context={
            "operation": "reorg-classify",
            "extension": meta.extension,
            "type_group": meta.type_group,
            "context_present": bool(context),
        },
    )
    parsed = extract_json_object(raw)
    if not parsed:
        return _fallback_category(meta.type_group)
    category = str(parsed.get("category", "")).strip()
    subcategory = parsed.get("subcategory")
    if isinstance(subcategory, str):
        subcategory = subcategory.strip()
    else:
        subcategory = None
    if not category:
        return _fallback_category(meta.type_group)
    return category, subcategory


def _resolve_collision(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    for i in range(1, 1000):
        candidate = parent / f"{stem}__{i}{suffix}"
        if not candidate.exists():
            return candidate
    return parent / f"{stem}__overflow{suffix}"


def plan_reorg(
    root: Path,
    *,
    recursive: bool,
    include_hidden: bool,
    max_files: int,
    max_snippet_chars: int,
    client: OllamaClient,
    model: str,
    policy: Dict[str, object],
    files: Optional[List[Path]] = None,
    context: Optional[str] = None,
) -> List[MoveOp]:
    ignore_patterns = policy.get("ignore_patterns", [])
    if not isinstance(ignore_patterns, list):
        ignore_patterns = []
    if files is None:
        files = gather_files(
            root,
            recursive=recursive,
            include_hidden=include_hidden,
            ignore_patterns=ignore_patterns,
        )
    else:
        selected: List[Path] = []
        for path in files:
            if path.is_symlink() or not path.is_file():
                continue
            if ".yordam-agent" in path.parts:
                continue
            rel_path = path.relative_to(root)
            if not include_hidden and is_hidden(rel_path):
                continue
            if _is_ignored(rel_path, ignore_patterns):
                continue
            selected.append(path)
        files = selected
    if max_files and len(files) > max_files:
        files = files[:max_files]
    moves: List[MoveOp] = []
    for path in files:
        meta = build_file_meta(path, max_snippet_chars=max_snippet_chars)
        category, subcategory = classify_file(
            meta, client=client, model=model, policy=policy, context=context
        )
        category = sanitize_folder_name(category)
        subcategory = sanitize_folder_name(subcategory) if subcategory else None
        dest_dir = root / category
        if subcategory:
            dest_dir = dest_dir / subcategory
        dest_path = _resolve_collision(dest_dir / path.name)
        if dest_path.resolve() == path.resolve():
            continue
        moves.append(MoveOp(src=path, dst=dest_path, category=category, subcategory=subcategory))
    return moves


def apply_moves(root: Path, moves: Iterable[MoveOp]) -> List[MoveOp]:
    applied: List[MoveOp] = []
    for move in moves:
        ensure_dir(move.dst.parent)
        shutil.move(str(move.src), str(move.dst))
        applied.append(move)
    return applied


def write_undo_log(root: Path, moves: Iterable[MoveOp]) -> Path:
    log_dir = root / ".yordam-agent"
    ensure_dir(log_dir)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"undo-{timestamp}.json"
    payload = {
        "version": 1,
        "root": str(root),
        "created_at": timestamp,
        "moves": [
            {"from": str(m.src), "to": str(m.dst)}
            for m in moves
        ],
    }
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return log_path


def write_plan_file(
    root: Path,
    moves: Iterable[MoveOp],
    path: Path,
    *,
    context: Optional[str] = None,
) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "version": 1,
        "root": str(root),
        "created_at": timestamp,
        "moves": [
            {
                "from": str(m.src),
                "to": str(m.dst),
                "category": m.category,
                "subcategory": m.subcategory,
            }
            for m in moves
        ],
    }
    if context:
        payload["context"] = context
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def resolve_reorg_selection(paths: List[Path]) -> Tuple[Path, Optional[List[Path]]]:
    if not paths:
        raise ValueError("No paths provided.")
    if len(paths) == 1 and paths[0].is_dir():
        return paths[0], None
    for path in paths:
        if path.is_dir():
            raise ValueError("Folders are not supported for multi-file reorg.")
        if not path.exists() or not path.is_file():
            raise ValueError(f"File not found: {path}")
    parents = {path.parent.resolve() for path in paths}
    if len(parents) != 1:
        raise ValueError("Selected files must share the same parent folder.")
    return parents.pop(), paths


def find_latest_log(root: Path) -> Optional[Path]:
    log_dir = root / ".yordam-agent"
    if not log_dir.exists():
        return None
    logs = sorted(log_dir.glob("undo-*.json"))
    return logs[-1] if logs else None


def undo_from_log(log_path: Path) -> Dict[str, int]:
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    moves = payload.get("moves", [])
    moved = 0
    skipped = 0
    for entry in reversed(moves):
        src = Path(entry.get("from", ""))
        dst = Path(entry.get("to", ""))
        if not dst.exists() or src.exists():
            skipped += 1
            continue
        ensure_dir(src.parent)
        shutil.move(str(dst), str(src))
        moved += 1
    return {"moved": moved, "skipped": skipped}
