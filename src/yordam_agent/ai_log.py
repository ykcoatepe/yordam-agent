from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .util import ensure_dir

_SAFE_CONTEXT_KEYS = {
    "extension",
    "operation",
    "source",
    "type_group",
}


def resolve_log_path(path_value: Optional[str], root: Optional[Path]) -> Optional[Path]:
    if not path_value:
        return None
    if not isinstance(path_value, str):
        return None
    expanded = Path(path_value).expanduser()
    if not expanded.is_absolute():
        base = root if root else Path.cwd()
        expanded = base / expanded
    return expanded


def _sanitize_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    if not context:
        return safe
    for key, value in context.items():
        if key not in _SAFE_CONTEXT_KEYS:
            continue
        if value is None or isinstance(value, (str, int, float, bool)):
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe


def build_log_entry(
    *,
    model: str,
    temperature: Optional[float],
    prompt_chars: int,
    system_chars: int,
    response_chars: int,
    duration_ms: int,
    success: bool,
    error_type: Optional[str],
    context: Optional[Dict[str, Any]],
    response_text: Optional[str] = None,
    include_response: bool = False,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "ollama.generate",
        "model": model,
        "prompt_chars": prompt_chars,
        "system_chars": system_chars,
        "response_chars": response_chars,
        "duration_ms": duration_ms,
        "success": success,
    }
    if temperature is not None:
        entry["temperature"] = temperature
    if error_type:
        entry["error_type"] = error_type
    safe_context = _sanitize_context(context)
    if safe_context:
        entry["context"] = safe_context
    if include_response and response_text is not None:
        entry["response"] = response_text
    return entry


def append_ai_log(log_path: Path, entry: Dict[str, Any]) -> None:
    try:
        ensure_dir(log_path.parent)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        return
