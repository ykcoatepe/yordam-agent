import fnmatch
import json
import mimetypes
import os
import re
import shutil
import subprocess
import unicodedata
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
    "People",
]

_PERSON_CONTEXT_KEYWORDS = {
    "person",
    "people",
    "person name",
    "name of the person",
    "by person",
    "per person",
    "kisi",
    "isim",
    "ad",
}

_PERSON_NAME_STOPWORDS = {
    "cv",
    "resume",
    "form",
    "formu",
    "document",
    "doc",
    "docx",
    "pdf",
    "report",
    "statement",
    "invoice",
    "tax",
    "agreement",
    "contract",
    "license",
    "permit",
    "application",
    "belge",
    "belgesi",
    "dilekce",
    "beyan",
    "kabul",
    "adli",
    "sicil",
    "kaydi",
    "askerlik",
    "gorev",
    "tahhut",
    "teslim",
    "ibra",
    "notary",
    "notarised",
    "power",
    "attorney",
    "icindir",
}


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
        if result.returncode == 0 and result.stdout.strip() == "Use OCR":
            return True
        if result.returncode == 0:
            return False
    except OSError:
        pass
    if not os.isatty(0):
        return False
    resp = input("Text could not be extracted. Use OCR? [y/N]: ").strip().lower()
    return resp.startswith("y")


def _ocr_snippet(path: Path, max_chars: int) -> str:
    if not shutil.which("tesseract"):
        return ""
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
    output = result.stdout.strip()
    if not output:
        return ""
    return output[:max_chars]


def build_file_meta(path: Path, max_snippet_chars: int, *, enable_ocr: bool = False) -> FileMeta:
    stat = path.stat()
    ext = file_extension(path)
    mime, _ = mimetypes.guess_type(str(path))
    group = _type_group_for(ext, mime)
    snippet = ""
    if is_text_extension(ext):
        snippet = read_text_snippet(path, max_snippet_chars)
    else:
        snippet = _spotlight_snippet(path, max_snippet_chars)
        if not snippet and enable_ocr:
            snippet = _ocr_snippet(path, max_snippet_chars)
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


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.lower()


def _context_mentions_person(context: str) -> bool:
    normalized = _normalize_match_text(context)
    for keyword in _PERSON_CONTEXT_KEYWORDS:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, normalized):
            return True
    return False


def _spotlight_value(path: Path, attribute: str) -> List[str]:
    try:
        result = subprocess.run(
            ["mdls", "-raw", "-name", attribute, str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    output = result.stdout.strip()
    if not output or output == "(null)":
        return []
    if output.startswith("(") and output.endswith(")"):
        items: List[str] = []
        for line in output[1:-1].splitlines():
            value = line.strip().strip(",").strip().strip("\"")
            if value:
                items.append(value)
        return items
    return [output.strip().strip("\"")]


def _extract_person_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    tokens = re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)
    if not tokens:
        return None

    def is_name_token(token: str) -> bool:
        normalized = _normalize_match_text(token)
        if not normalized or normalized in _PERSON_NAME_STOPWORDS:
            return False
        if any(ch.isdigit() for ch in token):
            return False
        return len(normalized) >= 2

    sequences: List[List[str]] = []
    current: List[str] = []
    for token in tokens:
        if is_name_token(token):
            current.append(token)
        else:
            if len(current) >= 2:
                sequences.append(current)
            current = []
    if len(current) >= 2:
        sequences.append(current)
    if not sequences:
        return None
    selected = max(enumerate(sequences), key=lambda item: (len(item[1]), item[0]))[1][:4]
    formatted: List[str] = []
    for token in selected:
        if any(ch.isupper() for ch in token):
            formatted.append(token)
        else:
            formatted.append(token[0].upper() + token[1:])
    return " ".join(formatted).strip() or None


def _extract_person_from_filename(name: str) -> Optional[str]:
    base = Path(name).stem
    cleaned = re.sub(r"[_\-.]+", " ", base)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    return _extract_person_from_text(cleaned)


def _extract_person_from_metadata(path: Path) -> Optional[str]:
    for attribute in ("kMDItemAuthors", "kMDItemCreator", "kMDItemTitle"):
        values = _spotlight_value(path, attribute)
        if not values:
            continue
        candidate = _extract_person_from_text(" ".join(values))
        if candidate:
            return candidate
    return None


def _extract_person_from_ai(
    meta: FileMeta, client: OllamaClient, model: str
) -> Optional[str]:
    system = (
        "You extract a person's full name from file metadata. "
        "Return a best guess if present; otherwise return null."
    )
    prompt = (
        "Extract the person's full name from this file metadata.\n"
        f"File name: {meta.name}\n"
        f"Extension: {meta.extension or 'none'}\n"
        f"Type group: {meta.type_group}\n"
        f"Size bytes: {meta.size_bytes}\n"
        f"Modified: {meta.modified_iso}\n"
        f"Snippet: {meta.snippet[:800]}\n\n"
        "Return ONLY JSON: {\"person\": \"...\"} or {\"person\": null}."
    )
    raw = client.generate(
        model=model,
        prompt=prompt,
        system=system,
        temperature=0.2,
        log_context={
            "operation": "reorg-extract-person",
            "extension": meta.extension,
            "type_group": meta.type_group,
        },
    )
    parsed = extract_json_object(raw)
    if not parsed:
        return None
    person = parsed.get("person")
    if isinstance(person, str):
        person = person.strip()
    else:
        person = None
    return person or None


def _classify_by_person(
    meta: FileMeta, client: OllamaClient, model: str
) -> Tuple[str, Optional[str]]:
    person = _extract_person_from_filename(meta.name)
    if not person:
        person = _extract_person_from_metadata(meta.path)
    if not person:
        person = _extract_person_from_text(meta.snippet)
    if not person:
        person = _extract_person_from_ai(meta, client, model)
    if not person:
        return "People", "Unknown"
    return "People", person


def _classify_with_context(
    meta: FileMeta, client: OllamaClient, model: str, context: str
) -> Tuple[Optional[str], Optional[str]]:
    system = (
        "You are a careful file organization assistant. "
        "Use the user's intent to decide whether a file should be moved. "
        "Only move files that clearly match the user's instruction. "
        "If unsure, do not move the file."
    )
    prompt = (
        f"User intent: {context}\n\n"
        "Given this file metadata, decide whether to move this file and where.\n"
        f"File name: {meta.name}\n"
        f"Extension: {meta.extension or 'none'}\n"
        f"Type group: {meta.type_group}\n"
        f"Size bytes: {meta.size_bytes}\n"
        f"Modified: {meta.modified_iso}\n"
        f"Snippet: {meta.snippet[:800]}\n\n"
        "Return ONLY JSON: "
        "{\"move\": true|false, \"category\": \"...\", \"subcategory\": \"...\"}. "
        "If move is false, set category and subcategory to null."
    )
    raw = client.generate(
        model=model,
        prompt=prompt,
        system=system,
        temperature=0.2,
        log_context={
            "operation": "reorg-classify-context",
            "extension": meta.extension,
            "type_group": meta.type_group,
        },
    )
    parsed = extract_json_object(raw)
    if not parsed:
        return None, None
    move_value = parsed.get("move")
    if not isinstance(move_value, bool):
        return None, None
    if not move_value:
        return None, None
    category = parsed.get("category")
    if category is None:
        return None, None
    if isinstance(category, str):
        category = category.strip()
    else:
        category = None
    subcategory = parsed.get("subcategory")
    if isinstance(subcategory, str):
        subcategory = subcategory.strip()
    else:
        subcategory = None
    if not category:
        return None, None
    return category, subcategory


def classify_file(
    meta: FileMeta,
    client: OllamaClient,
    model: str,
    policy: Dict[str, object],
    context: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    if context and _context_mentions_person(context):
        category, subcategory = _classify_by_person(meta, client, model)
        return category, sanitize_folder_name(subcategory) if subcategory else None
    if context:
        category, subcategory = _classify_with_context(meta, client, model, context)
        if not category:
            return None, None
        return category, sanitize_folder_name(subcategory) if subcategory else None
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
    ocr_mode: str = "off",
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
    ocr_decision: Optional[bool] = True if ocr_mode == "on" else None
    for path in files:
        meta = build_file_meta(path, max_snippet_chars=max_snippet_chars)
        needs_ocr = not meta.snippet and not is_text_extension(meta.extension)
        if ocr_mode == "ask" and needs_ocr and ocr_decision is None:
            ocr_decision = _prompt_for_ocr()
        if (ocr_mode == "on" or ocr_decision is True) and needs_ocr:
            meta = build_file_meta(
                path, max_snippet_chars=max_snippet_chars, enable_ocr=True
            )
        category, subcategory = classify_file(
            meta, client=client, model=model, policy=policy, context=context
        )
        if not category:
            continue
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


def write_preview_html(
    root: Path,
    moves: Iterable[MoveOp],
    path: Path,
    *,
    context: Optional[str] = None,
) -> Path:
    tree: Dict[str, Dict] = {}
    rows: List[Tuple[str, str]] = []
    for move in moves:
        try:
            rel_src = move.src.relative_to(root)
        except ValueError:
            rel_src = move.src
        try:
            rel_dst = move.dst.relative_to(root)
        except ValueError:
            rel_dst = move.dst
        rows.append((str(rel_src), str(rel_dst)))
        parts = rel_dst.parts
        if not parts:
            continue
        *dir_parts, filename = parts
        node = tree
        for part in dir_parts:
            node = node.setdefault(part, {})
        files = node.setdefault("__files__", [])
        if filename:
            files.append(filename)

    def render_tree(node: Dict[str, Dict], prefix: str = "") -> List[str]:
        lines: List[str] = []
        files = sorted(node.get("__files__", []))
        dirs = sorted([key for key in node.keys() if key != "__files__"])
        entries: List[Tuple[str, str]] = [(name, "file") for name in files] + [
            (name, "dir") for name in dirs
        ]
        for idx, (name, kind) in enumerate(entries):
            is_last = idx == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            suffix = "/" if kind == "dir" else ""
            lines.append(f"{prefix}{connector}{name}{suffix}")
            if kind == "dir":
                extension = "    " if is_last else "|   "
                lines.extend(render_tree(node[name], prefix + extension))
        return lines

    tree_lines = render_tree(tree)
    tree_text = "\n".join(tree_lines) if tree_lines else "(no moves)"
    escaped_tree = (
        tree_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    context_html = ""
    if context:
        safe_context = (
            context.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        context_html = f"<p><strong>Context:</strong> {safe_context}</p>"
    def _escape_cell(value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    if rows:
        rows_html = "\n".join(
            f"<tr><td>{_escape_cell(src)}</td><td>{_escape_cell(dst)}</td></tr>"
            for src, dst in rows
        )
    else:
        rows_html = "<tr><td colspan=\"2\"><em>No moves planned.</em></td></tr>"
    escaped_root = _escape_cell(str(root))
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Yordam Agent Preview</title>
  <style>
    :root {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --bg: #f7f7f9;
      --text: #111;
      --muted: #5b5b66;
      --card: #ffffff;
      --border: #d7d7dc;
      --pre-bg: #f0f0f3;
      --pre-text: #111;
      --table-row: #f9f9fb;
      --table-head: #f1f1f4;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f0f12;
        --text: #f2f2f6;
        --muted: #b1b1bd;
        --card: #17171d;
        --border: #2a2a33;
        --pre-bg: #101018;
        --pre-text: #f2f2f6;
        --table-row: #1b1b23;
        --table-head: #22222b;
      }}
    }}
    body {{
      margin: 24px;
      max-width: 1100px;
      background: var(--bg);
      color: var(--text);
    }}
    h1 {{ margin: 0 0 8px; }}
    h2 {{ margin: 0 0 12px; }}
    .meta {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 16px; }}
    .grid {{ display: grid; grid-template-columns: 1fr; gap: 20px; }}
    pre {{
      background: var(--pre-bg);
      color: var(--pre-text);
      padding: 16px;
      border-radius: 8px;
      overflow: auto;
      white-space: pre;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 13px;
      line-height: 1.4;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--card);
      color: var(--text);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
    }}
    th {{
      position: sticky;
      top: 0;
      background: var(--table-head);
      color: var(--text);
    }}
    tbody tr:nth-child(even) {{
      background: var(--table-row);
    }}
    .card {{
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      background: var(--card);
    }}
  </style>
</head>
<body>
  <h1>Yordam Agent Preview</h1>
  <div class="meta">Generated {timestamp} • Target root: {escaped_root}</div>
  {context_html}
  <div class="grid">
    <div class="card">
      <h2>Destination Tree</h2>
      <pre>{escaped_tree}</pre>
    </div>
    <div class="card">
      <h2>Move List</h2>
      <table>
        <thead><tr><th>From</th><th>To</th></tr></thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
    ensure_dir(path.parent)
    path.write_text(html, encoding="utf-8")
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
