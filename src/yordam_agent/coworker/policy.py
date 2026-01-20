from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from .registry import ToolRegistry


@dataclass(frozen=True)
class CoworkerPolicy:
    allowed_roots: List[Path]
    max_read_bytes: int
    max_write_bytes: int
    max_web_bytes: int
    max_query_chars: int
    require_approval: bool
    web_enabled: bool
    web_allowlist: List[str]


def policy_from_config(
    cfg: Dict[str, Any],
    selected_paths: Iterable[Path],
    extra_roots: Optional[Iterable[Path]] = None,
) -> CoworkerPolicy:
    allowed: List[Path] = []
    for raw in cfg.get("coworker_allowed_paths", []):
        allowed.append(Path(raw).expanduser().resolve())
    for path in selected_paths:
        resolved = path.expanduser().resolve()
        allowed.append(resolved.parent if resolved.is_file() else resolved)
    if extra_roots:
        for path in extra_roots:
            resolved = path.expanduser().resolve()
            allowed.append(resolved)
    deduped = _dedupe_paths(allowed)
    return CoworkerPolicy(
        allowed_roots=deduped,
        max_read_bytes=int(cfg.get("coworker_max_read_bytes", 200000)),
        max_write_bytes=int(cfg.get("coworker_max_write_bytes", 200000)),
        max_web_bytes=int(cfg.get("coworker_web_max_bytes", 200000)),
        max_query_chars=int(cfg.get("coworker_web_max_query_chars", 256)),
        require_approval=bool(cfg.get("coworker_require_approval", True)),
        web_enabled=bool(cfg.get("coworker_web_enabled", False)),
        web_allowlist=list(cfg.get("coworker_web_allowlist", [])),
    )


def validate_plan(
    plan: Dict[str, Any],
    policy: CoworkerPolicy,
    registry: ToolRegistry,
) -> List[str]:
    errors: List[str] = []
    tool_calls = plan.get("tool_calls", [])
    if not policy.allowed_roots:
        errors.append("No allowed roots configured for coworker plan.")
    for call in tool_calls:
        tool_name = call.get("tool")
        args = call.get("args", {})
        if not tool_name or not isinstance(tool_name, str):
            errors.append("Tool call missing tool name.")
            continue
        if registry.get(tool_name) is None:
            errors.append(f"Tool not allowlisted: {tool_name}")
            continue
        if not isinstance(args, dict):
            errors.append(f"Tool args must be object: {tool_name}")
            continue
        if tool_name.startswith("fs."):
            errors.extend(_validate_fs_call(tool_name, args, policy))
        elif tool_name.startswith("doc."):
            errors.extend(_validate_doc_call(tool_name, args, policy))
        elif tool_name == "web.fetch":
            errors.extend(_validate_web_call(args, policy))
    return errors


def _validate_fs_call(tool_name: str, args: Dict[str, Any], policy: CoworkerPolicy) -> List[str]:
    errors: List[str] = []
    raw_path = args.get("path")
    if not raw_path:
        errors.append(f"{tool_name} missing path")
        return errors
    path = _resolve_path(raw_path)
    if not _is_within_roots(path, policy.allowed_roots):
        errors.append(f"{tool_name} path outside allowlist: {path}")
        return errors
    if tool_name == "fs.read_text":
        max_bytes = int(args.get("max_bytes", policy.max_read_bytes))
        if max_bytes <= 0:
            errors.append("fs.read_text max_bytes must be positive")
        if max_bytes > policy.max_read_bytes:
            errors.append("fs.read_text max_bytes exceeds policy limit")
        if not path.exists() or not path.is_file():
            errors.append(f"fs.read_text file missing: {path}")
    elif tool_name == "fs.list_dir":
        if not path.exists() or not path.is_dir():
            errors.append(f"fs.list_dir directory missing: {path}")
    elif tool_name == "fs.propose_write_file":
        content = args.get("content")
        if content is None or not isinstance(content, str):
            errors.append("fs.propose_write_file requires content")
        if isinstance(content, str) and len(content.encode("utf-8")) > policy.max_write_bytes:
            errors.append("fs.propose_write_file content exceeds policy limit")
    elif tool_name == "fs.apply_write_file":
        content = args.get("content")
        if content is None or not isinstance(content, str):
            errors.append("fs.apply_write_file requires content")
        if isinstance(content, str) and len(content.encode("utf-8")) > policy.max_write_bytes:
            errors.append("fs.apply_write_file content exceeds policy limit")
        if path.exists():
            errors.append("fs.apply_write_file cannot overwrite existing file in v1")
        if not path.parent.exists():
            errors.append("fs.apply_write_file parent directory missing")
    elif tool_name in {"fs.move", "fs.rename"}:
        dst_raw = args.get("dst")
        if not dst_raw:
            errors.append(f"{tool_name} missing dst")
            return errors
        dst = _resolve_path(dst_raw)
        if not _is_within_roots(dst, policy.allowed_roots):
            errors.append(f"{tool_name} dst outside allowlist: {dst}")
        if not path.exists():
            errors.append(f"{tool_name} src missing: {path}")
        if dst.exists():
            errors.append(f"{tool_name} dst exists (overwrite not allowed)")
    return errors


def _validate_doc_call(tool_name: str, args: Dict[str, Any], policy: CoworkerPolicy) -> List[str]:
    errors: List[str] = []
    allowed_keys = {"path", "max_chars", "ocr_mode"}
    for key in args.keys():
        if key not in allowed_keys:
            errors.append(f"{tool_name} includes unsupported fields")
            break
    raw_path = args.get("path")
    if not raw_path:
        errors.append(f"{tool_name} missing path")
        return errors
    path = _resolve_path(raw_path)
    if not _is_within_roots(path, policy.allowed_roots):
        errors.append(f"{tool_name} path outside allowlist: {path}")
    if not path.exists() or not path.is_file():
        errors.append(f"{tool_name} file missing: {path}")
    ocr_mode = args.get("ocr_mode")
    if ocr_mode is not None and ocr_mode not in {"off", "ask", "on"}:
        errors.append(f"{tool_name} invalid ocr_mode")
    max_chars = args.get("max_chars")
    if max_chars is not None:
        max_chars_int: Optional[int] = None
        if isinstance(max_chars, bool):
            errors.append(f"{tool_name} max_chars must be integer")
        elif isinstance(max_chars, float) and not max_chars.is_integer():
            errors.append(f"{tool_name} max_chars must be integer")
        else:
            try:
                max_chars_int = int(max_chars)
            except (TypeError, ValueError):
                errors.append(f"{tool_name} max_chars must be integer")
        if max_chars_int is not None:
            if max_chars_int <= 0:
                errors.append(f"{tool_name} max_chars must be positive")
            if max_chars_int > policy.max_read_bytes:
                errors.append(f"{tool_name} max_chars exceeds policy limit")
    return errors


def _validate_web_call(args: Dict[str, Any], policy: CoworkerPolicy) -> List[str]:
    errors: List[str] = []
    if not policy.web_enabled:
        errors.append("web.fetch blocked (web not enabled)")
        return errors
    allowed_keys = {"url", "allowlist", "max_bytes", "method", "allow_query"}
    for key in args.keys():
        if key not in allowed_keys:
            errors.append("web.fetch includes unsupported fields")
            break
    for forbidden in ("body", "payload", "data", "content", "text", "file", "files"):
        if forbidden in args:
            errors.append("web.fetch cannot send local content")
    allow_query = args.get("allow_query")
    if allow_query is not None and not isinstance(allow_query, bool):
        errors.append("web.fetch allow_query must be boolean")
    url = args.get("url")
    if not url:
        errors.append("web.fetch missing url")
        return errors
    allowlist = args.get("allowlist")
    if not isinstance(allowlist, list) or not allowlist:
        errors.append("web.fetch requires per-task allowlist")
        return errors
    allowlist_entries = [str(entry) for entry in allowlist]
    normalized_allowlist = {entry.lower() for entry in allowlist_entries}
    if policy.web_allowlist:
        policy_allowlist = {str(entry).lower() for entry in policy.web_allowlist}
        if not normalized_allowlist.issubset(policy_allowlist):
            errors.append("web.fetch allowlist not permitted by policy")
            return errors
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme not in {"http", "https"}:
        errors.append("web.fetch only supports http(s)")
        return errors
    if parsed.query:
        if not allow_query:
            errors.append("web.fetch query requires allow_query=true")
        if len(parsed.query) > policy.max_query_chars:
            errors.append("web.fetch query exceeds policy limit")
    if not _host_allowed(host, allowlist_entries):
        errors.append("web.fetch url not in allowlist")
    max_bytes = int(args.get("max_bytes", policy.max_web_bytes))
    if max_bytes <= 0:
        errors.append("web.fetch max_bytes must be positive")
    if max_bytes > policy.max_web_bytes:
        errors.append("web.fetch max_bytes exceeds policy limit")
    method = str(args.get("method", "GET")).upper()
    if method != "GET":
        errors.append("web.fetch method must be GET")
    return errors


def _host_allowed(host: str, allowlist: Iterable[str]) -> bool:
    host = host.lower()
    for entry in allowlist:
        candidate = str(entry).lower()
        if host == candidate or host.endswith(f".{candidate}"):
            return True
    return False


def _resolve_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _is_within_roots(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set()
    deduped = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped
