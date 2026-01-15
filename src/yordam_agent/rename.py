import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .ollama import OllamaClient
from .organize import build_file_meta, gather_files, resolve_reorg_selection
from .policy import load_policy
from .util import ensure_dir, extract_json_object, is_hidden


@dataclass
class RenameOp:
    src: Path
    dst: Path
    reason: Optional[str] = None


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/]+", "-", name)
    cleaned = re.sub(r"[\r\n\t]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.strip(".")
    cleaned = re.sub(r"[^\w .,\-()&\[\]]", "", cleaned)
    if not cleaned or cleaned in {".", ".."}:
        return ""
    if len(cleaned) > 120:
        cleaned = cleaned[:120].rstrip()
    return cleaned


def _normalize_target_name(proposed: str, src: Path) -> Optional[str]:
    if not proposed:
        return None
    base = Path(str(proposed)).name
    base = _sanitize_filename(base)
    if not base:
        return None
    candidate = Path(base)
    stem = candidate.stem.strip()
    suffix = candidate.suffix
    if not stem:
        return None
    if suffix and suffix.lower() != src.suffix.lower():
        return f"{stem}{src.suffix}"
    if not suffix:
        return f"{stem}{src.suffix}"
    return f"{stem}{suffix}"


def _resolve_name_collision(name: str, reserved: Sequence[str]) -> str:
    if name not in reserved:
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    for i in range(1, 1000):
        candidate = f"{stem}__{i}{suffix}"
        if candidate not in reserved:
            return candidate
    return f"{stem}__overflow{suffix}"


def _unique_temp_name(parent: Path, suffix: str, reserved: set[Path]) -> Path:
    for i in range(1, 1000):
        candidate = parent / f".yordam_tmp_{i}{suffix}"
        if candidate not in reserved and not candidate.exists():
            reserved.add(candidate)
            return candidate
    fallback = parent / f".yordam_tmp_overflow{suffix}"
    reserved.add(fallback)
    return fallback


def _build_rename_prompt(
    instruction: str, metas: List[Dict[str, object]]
) -> Tuple[str, str]:
    system = (
        "You are a careful file renaming assistant. "
        "Return only JSON. Do not include markdown or explanations. "
        "Use only the provided files and keep their extensions."
    )
    payload = {
        "instruction": instruction,
        "files": metas,
        "output_format": {
            "renames": [
                {
                    "from": "original filename",
                    "to": "new filename (same extension)",
                    "reason": "optional short reason",
                }
            ]
        },
        "rules": [
            "Use only the provided file names in 'from'.",
            "Keep file extensions the same as the original.",
            "Do not include any path separators in 'to'.",
            "If a file should keep its name, omit it from renames.",
            (
                "Clean up any double spaces, dangling separators (like '- '), or empty "
                "brackets that result from removals."
            ),
            (
                "If removing a time or date token leaves a dangling word (like 'at' or "
                "'on'), remove that word too."
            ),
            "Do not leave the filename ending with a dangling word or separator.",
            "Ensure the output filename looks natural and complete.",
        ],
    }
    prompt = json.dumps(payload, indent=2)
    return system, prompt



def plan_rename(
    root: Path,
    *,
    instruction: str,
    recursive: bool,
    include_hidden: bool,
    max_files: int,
    client: OllamaClient,
    model: str,
    policy_path: Path,
    files: Optional[List[Path]] = None,
) -> List[RenameOp]:
    policy = load_policy(policy_path)
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
            selected.append(path)
        files = selected
    if max_files and len(files) > max_files:
        files = files[:max_files]
    if not files:
        return []

    metas: List[Dict[str, object]] = []
    for path in files:
        meta = build_file_meta(path, max_snippet_chars=0)
        metas.append(
            {
                "name": meta.name,
                "extension": meta.extension,
                "modified_iso": meta.modified_iso,
                "size_bytes": meta.size_bytes,
                "type_group": meta.type_group,
            }
        )

    system, prompt = _build_rename_prompt(instruction, metas)
    raw = client.generate(
        model=model,
        prompt=prompt,
        system=system,
        log_context={
            "operation": "rename",
            "source": "rename",
        },
    )
    parsed = extract_json_object(raw)
    if not parsed:
        return []
    renames = parsed.get("renames", [])
    if not isinstance(renames, list):
        return []
    lookup: Dict[str, Dict[str, object]] = {}
    for entry in renames:
        if not isinstance(entry, dict):
            continue
        from_name = str(entry.get("from", "")).strip()
        to_name = str(entry.get("to", "")).strip()
        if not from_name or not to_name:
            continue
        lookup[from_name] = entry

    src_names = {path.name for path in files}
    try:
        reserved = {
            path.name
            for path in root.iterdir()
            if path.is_file() and path.name not in src_names
        }
    except PermissionError:
        reserved = set()
    planned_targets: set[str] = set()
    planned: List[RenameOp] = []
    for path in files:
        entry = lookup.get(path.name)
        if not entry:
            continue
        proposed = str(entry.get("to", "")).strip()
        normalized = _normalize_target_name(proposed, path)
        if not normalized:
            continue
        candidate = normalized
        if candidate in reserved or candidate in planned_targets:
            candidate = _resolve_name_collision(candidate, reserved.union(planned_targets))
        if candidate == path.name:
            continue
        planned_targets.add(candidate)
        reason = entry.get("reason")
        reason_text = str(reason).strip() if isinstance(reason, str) else None
        planned.append(RenameOp(src=path, dst=path.parent / candidate, reason=reason_text))
    return planned


def apply_renames(ops: Iterable[RenameOp]) -> List[RenameOp]:
    ops_list = [op for op in ops if op.src != op.dst]
    if not ops_list:
        return []
    srcs = {op.src for op in ops_list}
    dsts = {op.dst for op in ops_list}
    reserved: set[Path] = set(srcs) | set(dsts)
    temp_ops: List[RenameOp] = []
    final_ops: List[RenameOp] = []
    for op in ops_list:
        if op.dst in srcs:
            temp = _unique_temp_name(op.src.parent, op.src.suffix, reserved)
            temp_ops.append(RenameOp(src=op.src, dst=temp, reason=op.reason))
            final_ops.append(RenameOp(src=temp, dst=op.dst, reason=op.reason))
        else:
            final_ops.append(op)
    applied: List[RenameOp] = []
    for op in temp_ops:
        ensure_dir(op.dst.parent)
        op.src.rename(op.dst)
        applied.append(op)
    for op in final_ops:
        ensure_dir(op.dst.parent)
        op.src.rename(op.dst)
        applied.append(op)
    return applied


def write_rename_plan_file(
    root: Path,
    ops: Iterable[RenameOp],
    path: Path,
    *,
    instruction: Optional[str] = None,
) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "version": 1,
        "root": str(root),
        "created_at": timestamp,
        "renames": [
            {"from": str(op.src), "to": str(op.dst), "reason": op.reason}
            for op in ops
        ],
    }
    if instruction:
        payload["instruction"] = instruction
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_rename_preview_html(
    root: Path,
    ops: Iterable[RenameOp],
    path: Path,
    *,
    instruction: Optional[str] = None,
) -> Path:
    rows: List[Tuple[str, str]] = []
    for op in ops:
        try:
            rel_src = op.src.relative_to(root)
        except ValueError:
            rel_src = op.src
        try:
            rel_dst = op.dst.relative_to(root)
        except ValueError:
            rel_dst = op.dst
        rows.append((str(rel_src), str(rel_dst)))
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    instruction_html = ""
    if instruction:
        safe_instruction = (
            instruction.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        instruction_html = f"<p><strong>Instruction:</strong> {safe_instruction}</p>"
    if rows:
        rows_html = "\n".join(
            f"<tr><td>{src}</td><td>{dst}</td></tr>" for src, dst in rows
        )
    else:
        rows_html = "<tr><td colspan=\"2\"><em>No renames planned.</em></td></tr>"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Yordam Rename Preview</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    h1 {{ font-size: 20px; }}
  </style>
</head>
<body>
  <h1>Rename Preview</h1>
  <p><strong>Generated:</strong> {timestamp}</p>
  {instruction_html}
  <table>
    <thead><tr><th>From</th><th>To</th></tr></thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""
    ensure_dir(path.parent)
    path.write_text(html, encoding="utf-8")
    return path


def resolve_rename_selection(paths: List[Path]) -> Tuple[Path, Optional[List[Path]]]:
    return resolve_reorg_selection(paths)
