#!/usr/bin/env python3
import csv
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Optional

from .documents_config import (
    documents_cache_path,
    documents_config_path,
    documents_lock_path,
    legacy_documents_cache_path,
    load_documents_config,
)
from .ollama import OllamaClient
from .util import ensure_dir

AI_MODEL_DEFAULT = "gpt-oss:20b"
AI_MAX_CHARS_DEFAULT = 20000
AI_TIMEOUT_SECONDS_DEFAULT = 90
ANSI_ESCAPE_RE = re.compile("\x1b\\[[0-9;?]*[A-Za-z]")


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def ai_log(message: str, log_path: Optional[Path]) -> None:
    if not log_path:
        return
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    ensure_dir(log_path.parent)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def save_config(config: dict, config_path: Path) -> None:
    tmp_path = config_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")
    tmp_path.replace(config_path)


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).casefold()
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def load_cache(cache_path: Path, legacy_cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    if legacy_cache_path.exists():
        try:
            return json.loads(legacy_cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(cache: dict, cache_path: Path) -> None:
    tmp_path = cache_path.with_suffix(".json.tmp")
    ensure_dir(cache_path.parent)
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(cache, handle)
    tmp_path.replace(cache_path)


def prune_cache(cache: dict) -> None:
    missing = [path for path in cache if not Path(path).exists()]
    for path in missing:
        cache.pop(path, None)


def hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_cached_hash(path: Path, cache: dict) -> str:
    key = str(path)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return ""
    cached = cache.get(key)
    if cached and cached.get("size") == stat.st_size and cached.get("mtime") == stat.st_mtime:
        return cached.get("hash", "")
    digest = hash_file(path)
    cache[key] = {"size": stat.st_size, "mtime": stat.st_mtime, "hash": digest}
    return digest


def file_is_stable(path: Path, min_age_seconds: int) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return False
    return age >= min_age_seconds


def match_extension(ext: str, rules: list[dict]) -> tuple[str, str] | tuple[None, None]:
    for rule in rules:
        if ext in rule.get("extensions", []):
            return rule.get("dest"), rule.get("reason")
    return None, None


def match_keyword(name: str, rules: list[dict]) -> tuple[str, str] | tuple[None, None]:
    for rule in rules:
        keyword = normalize(rule.get("keyword", ""))
        if keyword and keyword in name:
            return rule.get("dest"), keyword
    return None, None


def resolve_collision(destination: Path) -> Path:
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    parent = destination.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def find_ollama_path(config: dict) -> Optional[str]:
    override = config.get("ai_ollama_path")
    if override:
        return override
    for candidate in ("/opt/homebrew/bin/ollama", "/usr/local/bin/ollama", "/usr/bin/ollama"):
        if Path(candidate).exists():
            return candidate
    return shutil.which("ollama")


def _resolve_ai_timeout(config: dict) -> Optional[int]:
    raw = config.get("ai_timeout_seconds", AI_TIMEOUT_SECONDS_DEFAULT)
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        return AI_TIMEOUT_SECONDS_DEFAULT
    if timeout <= 0:
        return None
    return timeout


def ai_generate(prompt: str, config: dict) -> tuple[str, str]:
    backend = str(config.get("ai_backend", "http")).strip().lower()
    model = config.get("ai_model", AI_MODEL_DEFAULT)
    model_secondary = config.get("ai_model_secondary")
    if isinstance(model_secondary, str):
        model_secondary = model_secondary.strip() or None
    timeout = _resolve_ai_timeout(config)
    if backend == "cli":
        ollama_path = find_ollama_path(config)
        if not ollama_path:
            return "", "AI fallback skipped: ollama not found."
        cli_timeout = timeout if timeout is not None else AI_TIMEOUT_SECONDS_DEFAULT
        output, error = ollama_generate(ollama_path, model, prompt, cli_timeout)
        if error and model_secondary and model_secondary != model:
            fallback_output, fallback_error = ollama_generate(
                ollama_path, model_secondary, prompt, cli_timeout
            )
            if not fallback_error:
                return fallback_output, ""
            return "", f"{error}; fallback failed: {fallback_error}"
        return output, error
    base_url = config.get("ollama_base_url")
    if not base_url:
        return "", "AI fallback skipped: ollama base URL not configured."
    client = OllamaClient(
        base_url,
        fallback_model=model_secondary,
        gpt_oss_think_level=config.get("gpt_oss_think_level"),
    )
    try:
        response = client.generate(model=model, prompt=prompt, timeout=timeout)
    except RuntimeError as exc:
        return "", f"AI request failed: {exc}"
    return response, ""


def is_probably_text(path: Path) -> bool:
    try:
        sample = path.open("rb").read(4096)
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    return True


def extract_text_mdls(path: Path) -> str:
    try:
        result = subprocess.run(
            ["mdls", "-raw", "-name", "kMDItemTextContent", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except OSError:
        return ""
    text = result.stdout.strip()
    if not text or text == "(null)":
        return ""
    return text


def extract_text_textutil(path: Path) -> str:
    try:
        result = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def extract_text_raw(path: Path, max_chars: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(max_chars)
    except OSError:
        return ""


def extract_content(path: Path, max_chars: int) -> str:
    text = extract_text_mdls(path)
    if not text:
        text = extract_text_textutil(path)
    if not text and is_probably_text(path):
        text = extract_text_raw(path, max_chars)
    if not text:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n[truncated]"
    return text


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def sanitize_note(text: str, max_len: int = 120) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip() + "…"
    return cleaned


def summarize_directory(entry: Path, max_chars: int) -> str:
    try:
        items = sorted(entry.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return "[directory unreadable]"
    if not items:
        return "[empty directory]"
    max_items = 50
    names = []
    for item in items[:max_items]:
        suffix = "/" if item.is_dir() else ""
        names.append(f"{item.name}{suffix}")
    summary = ", ".join(names)
    if len(items) > max_items:
        summary += f" (+{len(items) - max_items} more)"
    text = f"Directory listing: {summary}"
    if len(text) > max_chars:
        return text[:max_chars] + "\n[truncated]"
    return text


def ollama_generate(ollama_path: str, model: str, prompt: str, timeout: int) -> tuple[str, str]:
    try:
        result = subprocess.run(
            [ollama_path, "run", "--hidethinking", model],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "", f"Ollama CLI failed: timed out after {timeout}s"
    except OSError as exc:
        return "", f"Ollama CLI failed: {exc}"

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if not stderr:
            stderr = strip_ansi(result.stdout).strip()
        if stderr:
            return "", f"Ollama CLI failed: {stderr}"
        return "", "Ollama CLI failed: unknown error"

    output = strip_ansi(result.stdout).strip()
    return output, ""


def sanitize_folder_name(name: str) -> str:
    cleaned = name.strip().strip("/\\")
    if not cleaned:
        return ""
    if cleaned.startswith("."):
        return ""
    cleaned = re.sub(r"[\\/:\n\r\t\0]+", " ", cleaned)
    cleaned = re.sub(r"[<>:\"|?*]+", "", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return ""
    if len(cleaned) > 60:
        cleaned = cleaned[:60].rstrip()
    return cleaned


def parse_ai_response(output: str) -> tuple[str, str]:
    if not output:
        return "", ""
    match = re.search(r"\{.*\}", output, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            folder = str(data.get("folder", "")).strip()
            reason = str(data.get("reason", "")).strip()
            return folder, reason
    first_line = output.strip().splitlines()[0] if output.strip() else ""
    return first_line.strip(), ""


def resolve_existing_folder(folder: str, existing: list[str]) -> tuple[str, bool]:
    lookup = {name.casefold(): name for name in existing}
    resolved = lookup.get(folder.casefold())
    if resolved:
        return resolved, True
    return folder, False


def ensure_category_dir(
    folder: str,
    config: dict,
    category_dirs: set[str],
    config_path: Path,
) -> None:
    if folder not in category_dirs:
        category_dirs.add(folder)
    config_list = config.get("category_dirs", [])
    if folder not in config_list:
        config_list.append(folder)
        config["category_dirs"] = config_list
        save_config(config, config_path)


def _build_ai_context(config: dict) -> str:
    context = str(config.get("ai_context", "")).strip()
    if not context:
        return ""
    return f"Additional context: {context}\n"


def ai_suggest_destination(
    entry: Path,
    config: dict,
    category_dirs: set[str],
    config_path: Path,
    log_path: Optional[Path],
    rule_hint: tuple[str, str] | None = None,
) -> tuple[Path | None, str]:
    max_chars = int(config.get("ai_max_chars", AI_MAX_CHARS_DEFAULT))
    if entry.is_dir():
        entry_type = "directory"
        content = summarize_directory(entry, max_chars)
    else:
        entry_type = "file"
        content = extract_content(entry, max_chars)
        if not content:
            content = "[no extractable text]"

    root = Path(config["root"]).expanduser()
    existing_dirs = sorted(
        set(category_dirs) | {path.name for path in root.iterdir() if path.is_dir()}
    )
    rule_line = ""
    if rule_hint:
        rule_folder, rule_reason = rule_hint
        rule_line = (
            "Rule-based suggestion: "
            f"{rule_folder} (reason: {sanitize_note(rule_reason)})\n"
            "Use this folder unless it is clearly incorrect.\n"
        )
    guidance_line = (
        "Folder guidance: Personal=personal life/home/household; "
        "Projects=project work/technical plans; "
        "Documents=general documents; "
        "Archive=long-term storage.\n"
    )
    context_line = _build_ai_context(config)
    prompt = "".join(
        [
            "You are a file organizer. Choose the best folder for the file.\n",
            (
                "If an existing folder fits, use it. Otherwise suggest a NEW folder name "
                "based on the file.\n"
            ),
            "Existing folders: ",
            ", ".join(existing_dirs),
            "\n",
            guidance_line,
            rule_line,
            context_line,
            f"Entry type: {entry_type}\n",
            f"Filename: {entry.name}\n",
            f"Extension: {entry.suffix or '[none]'}\n",
            "Content:\n",
            f"{content}\n\n",
            (
                "Return a single-line JSON object: "
                '{"folder": "...", "use_existing": true/false, "reason": "short"}\n'
            ),
            "Rules: folder name should be short, no slashes, no file extension.\n",
        ]
    )

    model = config.get("ai_model", AI_MODEL_DEFAULT)
    rule_label = f" rule={rule_hint[0]}" if rule_hint else ""
    ai_log(
        f"ai_suggest start name={entry.name} type={entry_type} model={model}{rule_label}",
        log_path,
    )
    output, error = ai_generate(prompt, config)
    if error:
        log(error)
        ai_log(f"ai_suggest error name={entry.name} error={sanitize_note(error)}", log_path)
        return None, ""
    if not output:
        log(f"AI fallback returned empty output for {entry.name}.")
        ai_log(f"ai_suggest empty name={entry.name}", log_path)
        return None, ""

    folder_raw, reason = parse_ai_response(output)
    folder = sanitize_folder_name(folder_raw)
    if not folder:
        repair_prompt = (
            "Return ONLY a folder name for this file. No other text.\n"
            f"Filename: {entry.name}\n"
            f"Extension: {entry.suffix or '[none]'}\n"
            "Content:\n"
            f"{content}\n"
        )
        ai_log(f"ai_suggest repair name={entry.name} model={model}", log_path)
        repair_output, error = ai_generate(repair_prompt, config)
        if error:
            log(error)
            ai_log(
                f"ai_suggest repair_error name={entry.name} error={sanitize_note(error)}",
                log_path,
            )
            return None, ""
        if repair_output:
            folder = sanitize_folder_name(repair_output.splitlines()[0].strip())
        if not folder:
            snippet = output.replace("\n", " ").strip()
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            log(f"AI fallback unusable for {entry.name}: {snippet}")
            ai_log(f"ai_suggest unusable name={entry.name}", log_path)
            return None, ""

    folder, is_existing = resolve_existing_folder(folder, existing_dirs)
    if folder in config.get("exclude_names", []):
        return None, ""

    destination = root / folder
    if not is_existing:
        destination.mkdir(parents=True, exist_ok=True)
    ensure_category_dir(folder, config, category_dirs, config_path)
    reason_label = reason or ("existing" if is_existing else "new")
    log(f"AI chose '{folder}' for {entry.name} ({reason_label}).")
    ai_log(
        f"ai_suggest result name={entry.name} folder={folder} reason={sanitize_note(reason_label)}",
        log_path,
    )
    return destination, f"ai:{reason_label}"


def ai_comment_duplicate(entry: Path, config: dict, log_path: Optional[Path]) -> str:
    model = config.get("ai_model", AI_MODEL_DEFAULT)
    max_chars = int(config.get("ai_max_chars", AI_MAX_CHARS_DEFAULT))
    content = extract_content(entry, max_chars)
    if not content:
        content = "[no extractable text]"
    context_line = _build_ai_context(config)
    prompt = (
        "You are a file organizer. Provide a short, single-line note about this duplicate file "
        "for a CSV report (<= 80 chars). No quotes or extra text.\n"
        f"Filename: {entry.name}\n"
        f"Extension: {entry.suffix or '[none]'}\n"
        f"{context_line}"
        "Content:\n"
        f"{content}\n"
    )
    ai_log(f"ai_duplicate_note start name={entry.name} model={model}", log_path)
    output, error = ai_generate(prompt, config)
    if error:
        log(error)
        ai_log(f"ai_duplicate_note error name={entry.name} error={sanitize_note(error)}", log_path)
        return ""
    if not output.strip():
        ai_log(f"ai_duplicate_note empty name={entry.name}", log_path)
        return ""
    note = output.strip().splitlines()[0]
    ai_log(
        f"ai_duplicate_note result name={entry.name} note={sanitize_note(note, 80)}",
        log_path,
    )
    return sanitize_note(note)


def append_report(report_path: Path, old_path: Path, new_path: Path, reason: str) -> None:
    report_exists = report_path.exists()
    with report_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if not report_exists:
            writer.writerow(["old_path", "new_path", "reason"])
        writer.writerow([str(old_path), str(new_path), reason])


def find_duplicate(target: Path, root: Path, cache: dict, skip_dirs: set[str]) -> Path | None:
    try:
        target_stat = target.stat()
    except FileNotFoundError:
        return None
    target_size = target_stat.st_size
    target_hash = None
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for filename in filenames:
            candidate = Path(dirpath) / filename
            if candidate == target:
                continue
            try:
                candidate_stat = candidate.stat()
            except FileNotFoundError:
                continue
            if candidate_stat.st_size != target_size:
                continue
            if target_hash is None:
                target_hash = get_cached_hash(target, cache)
                if not target_hash:
                    return None
            candidate_hash = get_cached_hash(candidate, cache)
            if candidate_hash and candidate_hash == target_hash:
                return candidate
    return None


def classify(entry: Path, config: dict) -> tuple[Path, str]:
    name = normalize(entry.name)
    ext = entry.suffix.lower() if entry.is_file() else ""

    dest, reason = match_extension(ext, config.get("extension_rules_high", []))
    if dest:
        return Path(config["root"]).expanduser() / dest, reason

    dest, keyword = match_keyword(name, config.get("keyword_rules", []))
    if dest:
        return Path(config["root"]).expanduser() / dest, f"keyword:{keyword}"

    dest, reason = match_extension(ext, config.get("extension_rules_low", []))
    if dest:
        return Path(config["root"]).expanduser() / dest, reason

    return Path(config["root"]).expanduser() / config.get("fallback_dest", "Archive"), "fallback"


def format_reason(reason: str, note: str) -> str:
    if not note:
        return reason
    if reason:
        return f"{reason} ({note})"
    return note


def _resolve_path(path_value: str, root: Path) -> Path:
    expanded = Path(path_value).expanduser()
    if expanded.is_absolute():
        return expanded
    return root / expanded


def _resolve_ai_log_path(config: dict, root: Path) -> Optional[Path]:
    path_value = config.get("ai_log_path")
    if not path_value:
        return None
    return _resolve_path(str(path_value), root)


def _list_ollama_models() -> list[str]:
    try:
        result = subprocess.run(
            ["ollama", "list"], check=False, capture_output=True, text=True
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    models: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("name"):
            continue
        name = stripped.split()[0]
        if name and name not in models:
            models.append(name)
    return models


def _merge_model_choices(
    config_models: Optional[list[str]],
    detected_models: list[str],
) -> list[str]:
    merged: list[str] = []
    if config_models:
        for item in config_models:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if value and value not in merged:
                merged.append(value)
    for item in detected_models:
        if item and item not in merged:
            merged.append(item)
    return merged


def _normalize_model_list(items: Optional[list[str]]) -> list[str]:
    normalized: list[str] = []
    if not items:
        return normalized
    for item in items:
        if not isinstance(item, str):
            continue
        value = item.strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _supports_reasoning_levels(model: str, config: dict) -> bool:
    normalized = _normalize_model_list(config.get("reasoning_level_models"))
    if normalized:
        return model.strip().lower() in normalized
    lowered = model.strip().lower()
    if not lowered:
        return False
    if "instruct" in lowered:
        return False
    return lowered.startswith("gpt-oss")


def _prompt_model_text(default_model: str) -> Optional[str]:
    prompt = f"Model (default {default_model}):"
    safe_prompt = prompt.replace("\"", "\\\"")
    safe_default = default_model.replace("\"", "")
    script = (
        "set theText to text returned of (display dialog "
        f"\"{safe_prompt}\" "
        f"default answer \"{safe_default}\" "
        "with title \"Yordam Agent\" "
        "buttons {\"Cancel\", \"OK\"} "
        "default button \"OK\")\n"
        "return theText"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script], check=False, capture_output=True, text=True
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _prompt_model(
    default_model: str, available_models: Optional[list[str]]
) -> Optional[tuple[str, bool]]:
    detected = _list_ollama_models()
    models = _merge_model_choices(available_models, detected)
    if models:
        choices = list(models)
        if default_model not in choices:
            choices.insert(0, default_model)
        choices.append("Other...")
        escaped_choices = [choice.replace("\"", "\\\"") for choice in choices]
        list_items = ", ".join([f"\"{choice}\"" for choice in escaped_choices])
        safe_prompt = "Select model".replace("\"", "\\\"")
        escaped_default = default_model.replace("\"", "\\\"")
        default_item = f"{{\"{escaped_default}\"}}" if default_model in choices else "{}"
        script = (
            f"set choices to {{{list_items}}}\n"
            "set theChoice to choose from list choices "
            f"with prompt \"{safe_prompt}\" "
            f"default items {default_item}\n"
            "if theChoice is false then return \"\"\n"
            "return item 1 of theChoice"
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        if result.returncode != 0:
            return None
        choice = result.stdout.strip()
        if not choice:
            return None
        if choice == "Other...":
            typed = _prompt_model_text(default_model)
            if typed is None:
                return None
            value = typed or default_model
            return value, True
        return choice, True

    typed = _prompt_model_text(default_model)
    if typed is None:
        return None
    value = typed or default_model
    return value, True


def _prompt_think_level(default_level: str) -> Optional[str]:
    valid_levels = {"low", "medium", "high", "off"}
    if default_level not in valid_levels:
        default_level = "low"
    prompt = "GPT-OSS thinking level:"
    safe_prompt = prompt.replace("\"", "\\\"")
    script = (
        "set choices to {\"low\", \"medium\", \"high\", \"off\"}\n"
        "set theChoice to choose from list choices "
        f"with prompt \"{safe_prompt}\" "
        f"default items {{\"{default_level}\"}}\n"
        "if theChoice is false then return \"\"\n"
        "return item 1 of theChoice"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script], check=False, capture_output=True, text=True
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if not value:
        return None
    return value


def _resolve_model_and_think(config: dict) -> tuple[str, Optional[str]]:
    default_model = str(config.get("ai_model") or AI_MODEL_DEFAULT)
    prompted = _prompt_model(default_model, config.get("available_models"))
    answered_model = False
    if prompted is None:
        model = default_model
    else:
        model, answered_model = prompted
    think_level = config.get("gpt_oss_think_level")
    if isinstance(think_level, str):
        think_level = think_level.strip()
    else:
        think_level = None
    if _supports_reasoning_levels(model, config) and answered_model:
        default_level = think_level or "low"
        prompted_level = _prompt_think_level(default_level)
        if prompted_level is not None:
            think_level = prompted_level
    return model, think_level


def main() -> int:
    log(
        "Organizer start. If you see 'Operation not permitted', grant Full Disk Access to "
        f"{sys.executable}."
    )
    config = load_documents_config()
    model, think_level = _resolve_model_and_think(config)
    config = dict(config)
    config["ai_model"] = model
    if think_level is not None:
        config["gpt_oss_think_level"] = think_level
    config_path = documents_config_path()
    root = Path(config["root"]).expanduser()
    min_age = int(config.get("min_age_seconds", 0))
    category_dirs = set(config.get("category_dirs", []))
    exclude_names = set(config.get("exclude_names", []))
    skip_extensions = set(ext.lower() for ext in config.get("skip_extensions", []))
    skip_dirs = set(exclude_names)

    root.mkdir(parents=True, exist_ok=True)

    report_path = _resolve_path(str(config["report_path"]), root)
    cache_path = documents_cache_path()
    legacy_cache_path = legacy_documents_cache_path()
    lock_path = documents_lock_path()
    log_path = _resolve_ai_log_path(config, root)

    ensure_dir(cache_path.parent)
    ensure_dir(lock_path.parent)
    ensure_dir(report_path.parent)

    with lock_path.open("w") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Another organizer run is active; exiting.")
            return 0

        cache = load_cache(cache_path, legacy_cache_path)
        prune_cache(cache)
        moved_count = 0

        for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if entry.name in exclude_names:
                continue
            if entry.name == ".DS_Store":
                continue
            if entry.name in category_dirs:
                continue
            if entry.is_symlink():
                continue
            if not file_is_stable(entry, min_age):
                continue
            if entry.is_file() and entry.suffix.lower() in skip_extensions:
                continue

            rule_destination, rule_reason = classify(entry, config)
            rule_hint = None
            if rule_reason != "fallback":
                rule_hint = (rule_destination.name, rule_reason)

            if entry.is_file():
                duplicate = find_duplicate(entry, root, cache, skip_dirs)
                if duplicate:
                    destination_dir = root / "Duplicates"
                    note = ""
                    ai_note = ai_comment_duplicate(entry, config, log_path)
                    if ai_note:
                        note = f"ai_note:{ai_note}"
                    reason = format_reason("duplicate", note)
                else:
                    ai_destination, ai_reason = ai_suggest_destination(
                        entry, config, category_dirs, config_path, log_path, rule_hint
                    )
                    if ai_destination:
                        destination_dir = ai_destination
                        note = ""
                        if ai_destination.name.casefold() != rule_destination.name.casefold():
                            note = (
                                f"ai_override: rules={rule_destination.name} "
                                f"ai={ai_destination.name}"
                            )
                        reason = format_reason(ai_reason, note)
                    else:
                        destination_dir = rule_destination
                        reason = rule_reason
            else:
                ai_destination, ai_reason = ai_suggest_destination(
                    entry, config, category_dirs, config_path, log_path, rule_hint
                )
                if ai_destination:
                    destination_dir = ai_destination
                    note = ""
                    if ai_destination.name.casefold() != rule_destination.name.casefold():
                        note = (
                            f"ai_override: rules={rule_destination.name} ai={ai_destination.name}"
                        )
                    reason = format_reason(ai_reason, note)
                else:
                    destination_dir = rule_destination
                    reason = rule_reason

            if destination_dir.exists() and not destination_dir.is_dir():
                log(f"Skipping move for {entry.name}: destination {destination_dir} is a file.")
                continue
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination_path = resolve_collision(destination_dir / entry.name)

            try:
                if destination_dir == entry:
                    log(f"Skipping move for {entry.name}: already in place.")
                    continue
                shutil.move(str(entry), str(destination_path))
            except (FileNotFoundError, shutil.Error) as exc:
                log(f"Failed to move {entry}: {exc}")
                continue

            append_report(report_path, entry, destination_path, reason)

            if destination_path.is_file():
                cache.pop(str(entry), None)
                get_cached_hash(destination_path, cache)

            moved_count += 1
            log(f"Moved {entry.name} -> {destination_path} ({reason})")

        save_cache(cache, cache_path)
        if moved_count:
            log(f"Done. Moved {moved_count} item(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
