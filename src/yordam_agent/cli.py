import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .ai_log import resolve_log_path
from .config import config_path, load_config
from .coworker.approval import build_approval, load_approval, write_approval
from .coworker.executor import (
    ApprovalError,
    PlanValidationError,
    apply_plan_with_state,
    preview_plan,
)
from .coworker.plan import ensure_plan_hash, load_plan, write_plan
from .coworker.planner import build_manual_plan, plan_from_instruction
from .coworker.policy import policy_from_config
from .coworker.registry import DEFAULT_REGISTRY
from .coworker.run_state import load_state, write_state
from .coworker.summarize import build_summary_plan
from .coworker_runtime.daemon import run_once
from .coworker_runtime.launchd import (
    DEFAULT_LAUNCHD_LABEL,
    DEFAULT_STDERR_PATH,
    DEFAULT_STDOUT_PATH,
    render_launchd_plist,
    resolve_program_path,
)
from .coworker_runtime.locks import release_task_locks
from .coworker_runtime.task_bundle import (
    append_event,
    ensure_task_bundle,
    update_task_snapshot,
)
from .coworker_runtime.task_bundle import (
    bundle_paths as build_bundle_paths,
)
from .coworker_runtime.task_store import TaskStore
from .documents_organizer import main as documents_main
from .ollama import OllamaClient
from .organize import (
    apply_moves,
    find_latest_log,
    plan_reorg,
    resolve_reorg_selection,
    undo_from_log,
    write_plan_file,
    write_preview_html,
    write_undo_log,
)
from .policy import load_policy
from .policy_wizard import run_policy_wizard
from .rename import (
    apply_renames,
    plan_rename,
    resolve_rename_selection,
    write_rename_plan_file,
    write_rename_preview_html,
)
from .rewrite import derive_output_path, normalize_tone, rewrite_text


def _pbpaste() -> str:
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False)
    except OSError:
        return ""
    return result.stdout


def _pbcopy(text: str) -> None:
    try:
        subprocess.run(["pbcopy"], input=text, text=True, check=False)
    except OSError:
        return


def _open_path(path: Path) -> None:
    try:
        subprocess.run(["open", str(path)], check=False)
    except OSError:
        return


def _preview_summary(moves: List) -> List[str]:
    total = len(moves)
    counts: Dict[str, int] = {}
    for move in moves:
        counts[move.category] = counts.get(move.category, 0) + 1
    lines = [f"{total} file(s) will be moved."]
    if counts:
        top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:3]
        summary = ", ".join([f"{name}: {count}" for name, count in top])
        lines.append(f"Top categories: {summary}")
    return lines


def _preview_message(moves: List, root: Path) -> str:
    lines = _preview_summary(moves)
    preview = moves[:10]
    if preview:
        lines.append("")
    for move in preview:
        try:
            rel_src = move.src.relative_to(root)
            rel_dst = move.dst.relative_to(root)
        except ValueError:
            rel_src = move.src
            rel_dst = move.dst
        lines.append(f"{rel_src} -> {rel_dst}")
    if len(moves) > len(preview):
        lines.append(f"... and {len(moves) - len(preview)} more")
    return "\n".join(lines)


def _preview_dialog_message(moves: List, root: Path) -> str:
    total = len(moves)
    counts: Dict[str, int] = {}
    for move in moves:
        counts[move.category] = counts.get(move.category, 0) + 1
    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:3]
    summary = ", ".join([f"{name}: {count}" for name, count in top]) if top else "n/a"
    samples: List[str] = []
    for move in moves[:5]:
        try:
            rel_src = move.src.relative_to(root)
        except ValueError:
            rel_src = move.src
        dst_label = move.category
        if move.subcategory:
            dst_label = f"{move.category}/{move.subcategory}"
        samples.append(f"{rel_src} -> {dst_label}")
    sample_text = "; ".join(samples) if samples else ""
    return (
        f"{total} file(s) will be moved. "
        f"Top categories: {summary}. "
        f"Sample: {sample_text}. "
        "Use 'Save Plan' for full details."
    )


def _preview_dialog(message: str, allow_apply: bool) -> Optional[str]:
    trimmed = message if len(message) <= 900 else message[:900] + "..."
    safe = trimmed.replace("\"", "\\\"")
    buttons = (
        "\"Cancel\", \"Save Plan\", \"Apply\""
        if allow_apply
        else "\"Cancel\", \"Save Plan\", \"OK\""
    )
    default_button = "Apply" if allow_apply else "OK"
    script = (
        "set theButton to button returned of (display dialog "
        f"\"{safe}\" "
        "with title \"Yordam Agent\" "
        f"buttons {{{buttons}}} "
        f"default button \"{default_button}\")\n"
        "return theButton"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script], check=False, capture_output=True, text=True
        )
    except OSError:
        print("Preview failed: osascript not available.")
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _rename_preview_summary(ops: List) -> List[str]:
    total = len(ops)
    return [f"{total} file(s) will be renamed."]


def _rename_preview_message(ops: List, root: Path) -> str:
    lines = _rename_preview_summary(ops)
    preview = ops[:10]
    if preview:
        lines.append("")
    for op in preview:
        try:
            rel_src = op.src.relative_to(root)
            rel_dst = op.dst.relative_to(root)
        except ValueError:
            rel_src = op.src
            rel_dst = op.dst
        lines.append(f"{rel_src} -> {rel_dst}")
    if len(ops) > len(preview):
        lines.append(f"... and {len(ops) - len(preview)} more")
    return "\n".join(lines)


def _rename_preview_dialog_message(ops: List, root: Path) -> str:
    total = len(ops)
    samples: List[str] = []
    for op in ops[:5]:
        try:
            rel_src = op.src.relative_to(root)
        except ValueError:
            rel_src = op.src
        try:
            rel_dst = op.dst.relative_to(root)
        except ValueError:
            rel_dst = op.dst
        samples.append(f"{rel_src} -> {rel_dst}")
    sample_text = "; ".join(samples) if samples else ""
    return (
        f"{total} file(s) will be renamed. "
        f"Sample: {sample_text}. "
        "Use 'Save Plan' for full details."
    )


def _choose_save_path(default_name: str) -> Optional[Path]:
    safe_name = default_name.replace("\"", "")
    script = (
        "set outFile to choose file name with prompt \"Save plan as:\" "
        f"default name \"{safe_name}\"\n"
        "return POSIX path of outFile"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script], check=False, capture_output=True, text=True
        )
    except OSError:
        print("Save failed: osascript not available.")
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if not value:
        return None
    return Path(value)


def _cli_preview(moves: List, root: Path, page_size: int = 20) -> bool:
    print("\n".join(_preview_summary(moves)))
    total = len(moves)
    if total > page_size:
        index = 0
        while index < total:
            chunk = moves[index : index + page_size]
            for move in chunk:
                rel_src = move.src.relative_to(root)
                rel_dst = move.dst.relative_to(root)
                print(f"{rel_src} -> {rel_dst}")
            index += page_size
            if index >= total:
                break
            resp = input("Show more? [Enter=next, q=quit]: ").strip().lower()
            if resp.startswith("q"):
                break
    choice = input("Apply these moves? [y/N]: ").strip().lower()
    return choice.startswith("y")


def _rename_cli_preview(ops: List, root: Path, page_size: int = 20) -> bool:
    print("\n".join(_rename_preview_summary(ops)))
    total = len(ops)
    if total > page_size:
        index = 0
        while index < total:
            chunk = ops[index : index + page_size]
            for op in chunk:
                rel_src = op.src.relative_to(root)
                rel_dst = op.dst.relative_to(root)
                print(f"{rel_src} -> {rel_dst}")
            index += page_size
            if index >= total:
                break
            resp = input("Show more? [Enter=next, q=quit]: ").strip().lower()
            if resp.startswith("q"):
                break
    choice = input("Apply these renames? [y/N]: ").strip().lower()
    return choice.startswith("y")


def cmd_reorg(args: argparse.Namespace) -> int:
    raw_paths = [Path(p).expanduser().resolve() for p in args.paths]
    try:
        root, selected_files = resolve_reorg_selection(raw_paths)
    except ValueError as exc:
        print(str(exc))
        return 1
    if selected_files is None and (not root.exists() or not root.is_dir()):
        print(f"Folder not found: {root}")
        return 1
    if selected_files is not None and not root.exists():
        print(f"Parent folder not found: {root}")
        return 1
    cfg = load_config()
    model, think_level = _resolve_model_and_think(
        args.model,
        cfg.get("model"),
        cfg.get("gpt_oss_think_level"),
        cfg.get("available_models"),
        cfg.get("reasoning_level_models"),
    )
    log_path = resolve_log_path(cfg.get("ai_log_path"), root)
    model_secondary = cfg.get("model_secondary")
    if isinstance(model_secondary, str):
        model_secondary = model_secondary.strip() or None
    client = OllamaClient(
        cfg["ollama_base_url"],
        log_path=log_path,
        fallback_model=model_secondary,
        gpt_oss_think_level=think_level,
        log_include_response=bool(cfg.get("ai_log_include_response")),
    )
    max_snippet_chars = args.max_snippet_chars or cfg["max_snippet_chars"]
    max_files = args.max_files if args.max_files is not None else cfg["max_files"]
    policy_path = Path(args.policy or cfg["policy_path"]).expanduser()
    policy = load_policy(policy_path)
    context = args.context if args.context is not None else cfg.get("reorg_context", "")
    if args.ocr:
        ocr_mode = "on"
    elif args.ocr_ask:
        ocr_mode = "ask"
    elif bool(cfg.get("ocr_enabled")):
        ocr_mode = "on"
    elif bool(cfg.get("ocr_prompt")):
        ocr_mode = "ask"
    else:
        ocr_mode = "off"
    if isinstance(context, str):
        context = context.strip()
    if not context:
        context = None

    moves = plan_reorg(
        root,
        recursive=args.recursive,
        include_hidden=args.include_hidden,
        max_files=max_files,
        max_snippet_chars=max_snippet_chars,
        client=client,
        model=model,
        policy=policy,
        files=selected_files,
        context=context,
        ocr_mode=ocr_mode,
    )

    if not moves:
        print("No moves planned.")
        return 0

    timestamp: Optional[str] = None
    plan_path: Optional[Path] = None
    if args.plan_file:
        plan_path = Path(args.plan_file).expanduser()
    elif args.open_plan or args.open_preview:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        plan_path = root / ".yordam-agent" / f"plan-{timestamp}.json"
    if plan_path:
        write_plan_file(root, moves, plan_path, context=context)
        print(f"Plan written: {plan_path}")

    preview_path: Optional[Path] = None
    if args.open_preview:
        if plan_path:
            preview_path = plan_path.with_suffix(".html")
        else:
            if not timestamp:
                timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            preview_path = root / ".yordam-agent" / f"preview-{timestamp}.html"
        write_preview_html(root, moves, preview_path, context=context)

    if plan_path and args.open_plan:
        _open_path(plan_path)
    if preview_path:
        _open_path(preview_path)

    if not (args.preview or args.preview_cli):
        for move in moves:
            rel_src = move.src.relative_to(root)
            rel_dst = move.dst.relative_to(root)
            print(f"{rel_src} -> {rel_dst}")
    else:
        print(f"{len(moves)} moves planned (preview enabled).")

    use_cli_preview = args.preview_cli
    if args.preview_cli and args.preview:
        print("Both preview flags set; using Finder dialog preview.")
        use_cli_preview = False

    if use_cli_preview:
        if not _cli_preview(moves, root):
            print("Preview cancelled.")
            return 0

    if args.preview and not use_cli_preview:
        message = _preview_dialog_message(moves, root)
        choice = _preview_dialog(message, allow_apply=args.apply)
        if choice == "Save Plan":
            default_name = f"yordam-plan-{root.name}.json"
            save_path = _choose_save_path(default_name)
            if not save_path:
                print("Save cancelled.")
                return 0
            write_plan_file(root, moves, save_path, context=context)
            print(f"Plan written: {save_path}")
            # Re-open dialog after saving to allow apply if requested
            if args.apply:
                choice = _preview_dialog(message, allow_apply=True)
            else:
                return 0
        if choice in {None, "Cancel", "OK"}:
            print("Preview cancelled.")
            return 0
        if choice == "Apply" and not args.apply:
            print("--apply not set; dry run only.")
            return 0

    if not args.apply:
        print(f"Dry run. {len(moves)} moves planned. Use --apply to execute.")
        return 0

    applied = apply_moves(root, moves)
    log_path = write_undo_log(root, applied)
    print(f"Applied {len(applied)} moves. Undo log: {log_path}")
    return 0


def _prompt_instruction() -> Optional[str]:
    if not os.isatty(0):
        return None
    try:
        value = input("Rename instruction: ").strip()
    except (EOFError, OSError):
        return None
    return value or None


def _list_ollama_models() -> List[str]:
    try:
        result = subprocess.run(
            ["ollama", "list"], check=False, capture_output=True, text=True
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    models: List[str] = []
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
    config_models: Optional[Iterable[str]],
    detected_models: List[str],
) -> List[str]:
    merged: List[str] = []
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


def _normalize_model_list(items: Optional[Iterable[str]]) -> List[str]:
    normalized: List[str] = []
    if not items:
        return normalized
    for item in items:
        if not isinstance(item, str):
            continue
        value = item.strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _supports_reasoning_levels(
    model: str, reasoning_level_models: Optional[Iterable[str]]
) -> bool:
    normalized = _normalize_model_list(reasoning_level_models)
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
    default_model: str, available_models: Optional[Iterable[str]]
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


def _resolve_model_and_think(
    args_model: Optional[str],
    cfg_model: Optional[str],
    cfg_think_level: Optional[str],
    available_models: Optional[Iterable[str]],
    reasoning_level_models: Optional[Iterable[str]],
) -> tuple[str, Optional[str]]:
    answered_model = False
    if args_model:
        model = args_model
        answered_model = True
    else:
        default_model = ""
        if isinstance(cfg_model, str):
            default_model = cfg_model.strip()
        if not default_model:
            default_model = "gpt-oss:20b"
        prompted = _prompt_model(default_model, available_models)
        if prompted is None:
            model = default_model
        else:
            model, answered_model = prompted

    think_level = cfg_think_level if isinstance(cfg_think_level, str) else None
    if _supports_reasoning_levels(model, reasoning_level_models) and answered_model:
        default_level = think_level.strip() if isinstance(think_level, str) else "low"
        prompted_level = _prompt_think_level(default_level)
        if prompted_level is not None:
            think_level = prompted_level
    return model, think_level


def cmd_rename(args: argparse.Namespace) -> int:
    raw_paths = [Path(p).expanduser().resolve() for p in args.paths]
    try:
        root, selected_files = resolve_rename_selection(raw_paths)
    except ValueError as exc:
        print(str(exc))
        return 1
    if selected_files is None and (not root.exists() or not root.is_dir()):
        print(f"Folder not found: {root}")
        return 1
    if selected_files is not None and not root.exists():
        print(f"Parent folder not found: {root}")
        return 1

    instruction = args.instruction.strip() if args.instruction else ""
    if not instruction:
        instruction = _prompt_instruction() or ""
    if not instruction:
        print("Rename instruction is required. Use --instruction.")
        return 1

    cfg = load_config()
    model, think_level = _resolve_model_and_think(
        args.model,
        cfg.get("model"),
        cfg.get("gpt_oss_think_level"),
        cfg.get("available_models"),
        cfg.get("reasoning_level_models"),
    )
    log_path = resolve_log_path(cfg.get("ai_log_path"), root)
    model_secondary = cfg.get("model_secondary")
    if isinstance(model_secondary, str):
        model_secondary = model_secondary.strip() or None
    client = OllamaClient(
        cfg["ollama_base_url"],
        log_path=log_path,
        fallback_model=model_secondary,
        gpt_oss_think_level=think_level,
        log_include_response=bool(cfg.get("ai_log_include_response")),
    )
    policy_path = Path(args.policy or cfg["policy_path"]).expanduser()

    try:
        ops = plan_rename(
            root,
            instruction=instruction,
            recursive=args.recursive,
            include_hidden=args.include_hidden,
            max_files=args.max_files if args.max_files is not None else cfg["max_files"],
            client=client,
            model=model,
            policy_path=policy_path,
            files=selected_files,
        )
    except PermissionError as exc:
        print(str(exc))
        return 1

    if not ops:
        print("No renames planned.")
        return 0

    timestamp: Optional[str] = None
    plan_path: Optional[Path] = None
    if args.plan_file:
        plan_path = Path(args.plan_file).expanduser()
    elif args.open_plan or args.open_preview:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        plan_path = root / ".yordam-agent" / f"rename-plan-{timestamp}.json"
    if plan_path:
        write_rename_plan_file(root, ops, plan_path, instruction=instruction)
        print(f"Plan written: {plan_path}")

    preview_path: Optional[Path] = None
    if args.open_preview:
        if plan_path:
            preview_path = plan_path.with_suffix(".html")
        else:
            if not timestamp:
                timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            preview_path = root / ".yordam-agent" / f"rename-preview-{timestamp}.html"
        write_rename_preview_html(root, ops, preview_path, instruction=instruction)

    if plan_path and args.open_plan:
        _open_path(plan_path)
    if preview_path:
        _open_path(preview_path)

    if not (args.preview or args.preview_cli):
        for op in ops:
            rel_src = op.src.relative_to(root)
            rel_dst = op.dst.relative_to(root)
            print(f"{rel_src} -> {rel_dst}")
    else:
        print(f"{len(ops)} renames planned (preview enabled).")

    use_cli_preview = args.preview_cli
    if args.preview_cli and args.preview:
        print("Both preview flags set; using Finder dialog preview.")
        use_cli_preview = False

    if use_cli_preview:
        if not _rename_cli_preview(ops, root):
            print("Preview cancelled.")
            return 0

    if args.preview and not use_cli_preview:
        message = _rename_preview_dialog_message(ops, root)
        choice = _preview_dialog(message, allow_apply=args.apply)
        if choice == "Save Plan":
            default_name = f"yordam-rename-{root.name}.json"
            save_path = _choose_save_path(default_name)
            if not save_path:
                print("Save cancelled.")
                return 0
            write_rename_plan_file(root, ops, save_path, instruction=instruction)
            print(f"Plan written: {save_path}")
            if args.apply:
                choice = _preview_dialog(message, allow_apply=True)
            else:
                return 0
        if choice in {None, "Cancel", "OK"}:
            print("Preview cancelled.")
            return 0
        if choice == "Apply" and not args.apply:
            print("--apply not set; dry run only.")
            return 0

    if not args.apply:
        print(f"Dry run. {len(ops)} renames planned. Use --apply to execute.")
        return 0

    applied = apply_renames(ops)
    print(f"Applied {len(applied)} renames.")
    return 0


def cmd_undo(args: argparse.Namespace) -> int:
    root = Path(args.folder).expanduser().resolve() if args.folder else Path.cwd()
    log_path = None
    if args.id:
        candidate = Path(args.id).expanduser()
        if candidate.exists():
            log_path = candidate
        else:
            log_path = root / ".yordam-agent" / f"undo-{args.id}.json"
    else:
        log_path = find_latest_log(root)

    if not log_path or not log_path.exists():
        print("Undo log not found.")
        return 1

    result = undo_from_log(log_path)
    print(f"Undo complete. Moved: {result['moved']}, Skipped: {result['skipped']}")
    return 0


def cmd_rewrite(args: argparse.Namespace) -> int:
    cfg = load_config()
    model, think_level = _resolve_model_and_think(
        args.model,
        cfg.get("rewrite_model"),
        cfg.get("gpt_oss_think_level"),
        cfg.get("available_models"),
        cfg.get("reasoning_level_models"),
    )
    tone = normalize_tone(args.tone)

    source = ""
    text = ""
    input_path: Path | None = None

    if args.input:
        input_path = Path(args.input).expanduser()
        if not input_path.exists() or not input_path.is_file():
            print(f"Input file not found: {input_path}")
            return 1
        text = input_path.read_text(encoding="utf-8", errors="replace")
        source = "file"
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
        source = "stdin"
    else:
        text = _pbpaste()
        source = "clipboard"

    if not text.strip():
        print("No input text found.")
        return 1

    log_root = input_path.parent if input_path else Path.cwd()
    log_path = resolve_log_path(cfg.get("ai_log_path"), log_root)
    model_secondary = cfg.get("rewrite_model_secondary")
    if isinstance(model_secondary, str):
        model_secondary = model_secondary.strip() or None
    client = OllamaClient(
        cfg["ollama_base_url"],
        log_path=log_path,
        fallback_model=model_secondary,
        gpt_oss_think_level=think_level,
        log_include_response=bool(cfg.get("ai_log_include_response")),
    )
    log_context = {"operation": "rewrite", "source": source}
    if input_path and input_path.suffix:
        log_context["extension"] = input_path.suffix.lower()

    rewritten = rewrite_text(
        text,
        tone=tone,
        client=client,
        model=model,
        log_context=log_context,
    )

    if args.in_place:
        if not input_path:
            print("--in-place requires --input")
            return 1
        input_path.write_text(rewritten, encoding="utf-8")
        print(f"Rewrote in place: {input_path}")
        return 0

    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.write_text(rewritten, encoding="utf-8")
        print(f"Wrote: {out_path}")
        return 0

    if input_path:
        out_path = Path(derive_output_path(str(input_path)))
        out_path.write_text(rewritten, encoding="utf-8")
        print(f"Wrote: {out_path}")
        return 0

    sys.stdout.write(rewritten)
    if args.copy or source == "clipboard":
        _pbcopy(rewritten)
    return 0


def cmd_config(_: argparse.Namespace) -> int:
    cfg = load_config()
    print(f"Config: {config_path()}")
    for key, value in cfg.items():
        print(f"{key}: {value}")
    policy_path = Path(cfg["policy_path"]).expanduser()
    print(f"policy_exists: {policy_path.exists()}")
    return 0


def cmd_policy_wizard(args: argparse.Namespace) -> int:
    cfg = load_config()
    policy_path = Path(args.policy or cfg["policy_path"]).expanduser()
    path, overwrite = run_policy_wizard(policy_path)
    action = "overwrote" if overwrite else "updated"
    print(f"Policy {action}: {path}")
    return 0


def cmd_documents(_: argparse.Namespace) -> int:
    return documents_main()


def _resolve_coworker_paths(paths: List[str]) -> List[Path]:
    resolved: List[Path] = []
    for raw in paths:
        resolved.append(Path(raw).expanduser().resolve())
    return resolved


def _resolve_optional_roots(raw_roots: Optional[List[str]]) -> List[Path]:
    if not raw_roots:
        return []
    resolved: List[Path] = []
    for raw in raw_roots:
        resolved.append(Path(raw).expanduser().resolve())
    return resolved


def _runtime_state_dir(cfg: Dict[str, object], override: Optional[str]) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    raw = cfg.get("coworker_runtime_state_dir")
    if raw:
        return Path(str(raw)).expanduser().resolve()
    return Path.home() / ".config" / "yordam-agent" / "coworker"


def _runtime_store(cfg: Dict[str, object], override: Optional[str]) -> TaskStore:
    state_dir = _runtime_state_dir(cfg, override)
    db_path = state_dir / "tasks.db"
    return TaskStore(db_path)


def _runtime_enabled(cfg: Dict[str, object]) -> bool:
    raw = cfg.get("coworker_runtime_enabled")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(raw, int):
        return raw != 0
    return False


def _runtime_workers(cfg: Dict[str, object], override: Optional[int]) -> int:
    if override is not None:
        return max(1, int(override))
    raw = cfg.get("coworker_runtime_workers", 1)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def _require_runtime_enabled(cfg: Dict[str, object]) -> bool:
    if _runtime_enabled(cfg):
        return True
    print(
        "Coworker runtime is disabled. Set coworker_runtime_enabled=true in config or "
        "export YORDAM_COWORKER_RUNTIME_ENABLED=1."
    )
    return False


def cmd_coworker_preview(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan).expanduser()
    plan = load_plan(plan_path)
    cfg = load_config()
    selected_paths = _resolve_coworker_paths(args.paths or [])
    extra_roots = _resolve_optional_roots(args.allow_root)
    policy = policy_from_config(cfg, selected_paths, extra_roots)
    try:
        lines = preview_plan(
            plan,
            policy,
            DEFAULT_REGISTRY,
            include_diffs=args.include_diffs,
        )
    except PlanValidationError as exc:
        print(str(exc))
        return 1
    print("\n".join(lines))
    return 0


def cmd_coworker_checkpoints(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan).expanduser()
    plan = load_plan(plan_path)
    checkpoints = plan.get("checkpoints", [])
    if not checkpoints:
        print("No checkpoints defined.")
        return 0
    for checkpoint in checkpoints:
        print(checkpoint)
    return 0


def cmd_coworker_approve(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan).expanduser()
    plan = load_plan(plan_path)
    plan_hash = ensure_plan_hash(plan)
    write_plan(plan_path, plan)
    approval = build_approval(plan_hash, checkpoint_id=args.checkpoint_id)
    approval_path = (
        Path(args.approval_file).expanduser()
        if args.approval_file
        else plan_path.with_suffix(".approval.json")
    )
    write_approval(approval_path, approval)
    print(f"Approval written: {approval_path}")
    return 0


def cmd_coworker_apply(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan).expanduser()
    plan = load_plan(plan_path)
    cfg = load_config()
    selected_paths = _resolve_coworker_paths(args.paths or [])
    extra_roots = _resolve_optional_roots(args.allow_root)
    policy = policy_from_config(cfg, selected_paths, extra_roots)
    approval = None
    if args.approval_file:
        approval = load_approval(Path(args.approval_file).expanduser())
    resume_state = None
    if args.resume_state:
        resume_state = load_state(Path(args.resume_state).expanduser())
    try:
        results, state = apply_plan_with_state(
            plan,
            policy,
            DEFAULT_REGISTRY,
            approval=approval,
            resume_state=resume_state,
            stop_at_checkpoints=args.checkpoint,
        )
    except (PlanValidationError, ApprovalError) as exc:
        print(str(exc))
        return 1
    for result in results:
        print(result)
    if state:
        state_path = (
            Path(args.resume_state).expanduser()
            if args.resume_state
            else plan_path.with_suffix(".state.json")
        )
        write_state(state_path, state)
        print(f"Checkpoint reached. Resume state: {state_path}")
    return 0


def cmd_coworker_runtime_submit(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not _require_runtime_enabled(cfg):
        return 1
    plan_path = Path(args.plan).expanduser().resolve()
    plan = load_plan(plan_path)
    plan_hash = ensure_plan_hash(plan)
    write_plan(plan_path, plan)

    task_id = f"tsk_{uuid.uuid4().hex}"
    bundle_root = (
        Path(args.bundle_root).expanduser().resolve()
        if args.bundle_root
        else _runtime_state_dir(cfg, args.state_dir) / "bundles" / task_id
    )

    selected_paths = _resolve_coworker_paths(args.paths or [])
    extra_roots = _resolve_optional_roots(args.allow_root)
    policy = policy_from_config(cfg, selected_paths, extra_roots)
    if not policy.allowed_roots:
        print(
            "No allowed roots configured. Provide --paths/--allow-root or set "
            "coworker_allowed_paths."
        )
        return 1

    store = _runtime_store(cfg, args.state_dir)

    metadata: Dict[str, object] = {}
    if selected_paths:
        metadata["selected_paths"] = [str(path) for path in selected_paths]
    if extra_roots:
        metadata["allow_roots"] = [str(path) for path in extra_roots]
    if args.metadata:
        try:
            extra = json.loads(args.metadata)
        except json.JSONDecodeError as exc:
            print(f"Invalid metadata JSON: {exc}")
            return 1
        if isinstance(extra, dict):
            metadata.update(extra)
    metadata["allowed_roots"] = [str(path) for path in policy.allowed_roots]

    bundle_paths = ensure_task_bundle(
        bundle_root,
        task_id=task_id,
        plan=plan,
        metadata=metadata or None,
    )

    store.create_task(
        task_id=task_id,
        plan_hash=plan_hash,
        plan_path=plan_path,
        bundle_path=bundle_root,
        metadata=metadata or None,
    )

    append_event(
        bundle_paths,
        {"task_id": task_id, "event": "task_created", "state": "queued"},
    )
    print(f"Task queued: {task_id}")
    print(f"Bundle: {bundle_root}")
    return 0


def cmd_coworker_runtime_list(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not _require_runtime_enabled(cfg):
        return 1
    store = _runtime_store(cfg, args.state_dir)
    tasks = store.list_tasks(state=args.state, limit=100, offset=0)
    if not tasks:
        print("No tasks.")
        return 0
    for task in tasks:
        print(f"{task.id} state={task.state} plan={task.plan_path}")
    return 0


def cmd_coworker_runtime_status(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not _require_runtime_enabled(cfg):
        return 1
    store = _runtime_store(cfg, args.state_dir)
    counts = store.count_tasks_by_state(state=args.state)
    if not counts:
        print("No tasks.")
        return 0
    for state, count in sorted(counts.items()):
        print(f"{state}: {count}")
    return 0


def cmd_coworker_runtime_logs(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not _require_runtime_enabled(cfg):
        return 1
    store = _runtime_store(cfg, args.state_dir)
    task = store.get_task(args.task)
    events_path = Path(task.bundle_path) / "events.jsonl"
    if not events_path.exists():
        print("No events yet.")
        return 0
    print(events_path.read_text(encoding="utf-8"), end="")
    return 0


def cmd_coworker_runtime_approve(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not _require_runtime_enabled(cfg):
        return 1
    store = _runtime_store(cfg, args.state_dir)
    approved_by = args.approved_by or os.environ.get("USER", "unknown")
    store.record_approval(
        plan_hash=args.plan_hash,
        checkpoint_id=args.checkpoint_id,
        approved_by=approved_by,
    )
    print("Approval recorded.")
    return 0


def cmd_coworker_runtime_cancel(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not _require_runtime_enabled(cfg):
        return 1
    store = _runtime_store(cfg, args.state_dir)
    task = store.get_task(args.task)
    if task.state in {"completed", "failed", "canceled"}:
        print(f"Task already {task.state}; cancel ignored.")
        return 0
    was_running = task.state == "running"
    task = store.update_task_state(
        args.task,
        state="canceled",
        error="canceled by user",
        clear_lock=not was_running,
    )
    bundle_root = Path(task.bundle_path)
    selected_paths = task.metadata.get("selected_paths")
    if selected_paths and not was_running:
        locks_dir = store.db_path.parent / "locks"
        release_task_locks(
            [Path(p) for p in selected_paths],
            locks_dir=locks_dir,
            task_id=task.id,
        )
    if bundle_root.exists():
        plan = None
        bundle_plan_path = bundle_root / "plan.json"
        if bundle_plan_path.exists():
            plan = load_plan(bundle_plan_path)
        else:
            task_plan_path = Path(task.plan_path)
            if task_plan_path.exists():
                plan = load_plan(task_plan_path)
        if plan is not None:
            bundle_paths = ensure_task_bundle(
                bundle_root,
                task_id=task.id,
                plan=plan,
                metadata=task.metadata,
            )
        else:
            bundle_paths = build_bundle_paths(bundle_root)
        append_event(
            bundle_paths,
            {"task_id": task.id, "event": "task_canceled", "state": "canceled"},
        )
        update_task_snapshot(
            bundle_paths,
            task_id=task.id,
            plan_hash=task.plan_hash,
            state="canceled",
            metadata=task.metadata,
            error="canceled by user",
        )
    print(f"Task canceled: {task.id}")
    return 0


def cmd_coworker_runtime_daemon(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not _require_runtime_enabled(cfg):
        return 1
    store = _runtime_store(cfg, args.state_dir)
    worker_base = args.worker_id or f"worker-{os.getpid()}"
    workers = _runtime_workers(cfg, args.workers)
    poll = float(args.poll_seconds)
    try:
        while True:
            had_task = False
            for idx in range(workers):
                worker_id = worker_base if workers == 1 else f"{worker_base}-{idx + 1}"
                result = run_once(store, worker_id=worker_id)
                if result.task is not None:
                    had_task = True
                if args.once:
                    print(result.message)
            if args.once:
                break
            if not had_task:
                time.sleep(poll)
    except KeyboardInterrupt:
        print("Daemon stopped.")
    return 0


def cmd_coworker_runtime_print_plist(args: argparse.Namespace) -> int:
    cfg = load_config()
    program = resolve_program_path(args.program)
    if program is None:
        print("Unable to resolve program path. Use --program to specify a binary.")
        return 1

    state_dir = _runtime_state_dir(cfg, args.state_dir)
    workers = args.workers
    if workers is None:
        resolved_workers = _runtime_workers(cfg, None)
        if resolved_workers != 1:
            workers = resolved_workers
    if workers is not None and workers < 1:
        print("Worker count must be >= 1.")
        return 1
    if args.poll_seconds is not None and args.poll_seconds <= 0:
        print("Poll seconds must be > 0.")
        return 1

    stdout_path = (
        Path(args.stdout_path).expanduser().resolve()
        if args.stdout_path
        else DEFAULT_STDOUT_PATH
    )
    stderr_path = (
        Path(args.stderr_path).expanduser().resolve()
        if args.stderr_path
        else DEFAULT_STDERR_PATH
    )

    plist_text = render_launchd_plist(
        program=program,
        label=args.label,
        state_dir=state_dir,
        workers=workers,
        poll_seconds=args.poll_seconds,
        worker_id=args.worker_id,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        enable_runtime_env=args.enable_runtime_env,
    )
    print(plist_text, end="")
    return 0


def cmd_coworker_plan(args: argparse.Namespace) -> int:
    cfg = load_config()
    selected_paths = _resolve_coworker_paths(args.paths or [])
    plan_path = _default_coworker_plan_path(args.out, selected_paths)
    if args.instruction:
        model, think_level = _resolve_model_and_think(
            args.model,
            cfg.get("model"),
            cfg.get("gpt_oss_think_level"),
            cfg.get("available_models"),
            cfg.get("reasoning_level_models"),
        )
        cfg = dict(cfg)
        if think_level is not None:
            cfg["gpt_oss_think_level"] = think_level
        plan = plan_from_instruction(
            instruction=args.instruction,
            selected_paths=selected_paths,
            cfg=cfg,
            registry=DEFAULT_REGISTRY,
            model=model,
            max_snippet_chars=args.max_snippet_chars,
        )
    else:
        if not args.tool or not args.args:
            print("Manual planning requires --tool and --args.")
            return 1
        if len(args.tool) != len(args.args):
            print("--tool and --args must be provided in pairs.")
            return 1
        tool_calls = []
        for tool_name, raw_args in zip(args.tool, args.args):
            try:
                parsed = json.loads(raw_args)
            except json.JSONDecodeError as exc:
                print(f"Invalid JSON args for {tool_name}: {exc}")
                return 1
            tool_calls.append({"tool": tool_name, "args": parsed})
        plan = build_manual_plan(tool_calls, instruction=None)
    ensure_plan_hash(plan)
    write_plan(plan_path, plan)
    print(f"Plan written: {plan_path}")
    return 0


def cmd_coworker_summarize(args: argparse.Namespace) -> int:
    cfg = load_config()
    paths = _resolve_coworker_paths(args.paths or [])
    if not paths:
        print("Provide at least one file to summarize.")
        return 1
    for path in paths:
        if not path.is_file():
            print(f"Not a file: {path}")
            return 1
    model, think_level = _resolve_model_and_think(
        args.model,
        cfg.get("model"),
        cfg.get("gpt_oss_think_level"),
        cfg.get("available_models"),
        cfg.get("reasoning_level_models"),
    )
    cfg = dict(cfg)
    if think_level is not None:
        cfg["gpt_oss_think_level"] = think_level
    max_chars = args.max_chars or int(cfg.get("coworker_max_read_bytes", 200000))
    plan = build_summary_plan(
        paths=paths,
        cfg=cfg,
        model=model,
        max_chars=max_chars,
        task=args.task,
    )
    plan_path = _default_coworker_plan_path(args.out, paths)
    write_plan(plan_path, plan)
    print(f"Plan written: {plan_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yordam-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    reorg = sub.add_parser("reorg", help="Reorganize files using AI")
    reorg.add_argument("paths", nargs="+", help="Target folder or file paths")
    reorg.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    reorg.add_argument("--recursive", action="store_true", help="Include subfolders")
    reorg.add_argument("--include-hidden", action="store_true", help="Include hidden files")
    reorg.add_argument("--max-files", type=int, default=None, help="Max files to process")
    reorg.add_argument(
        "--max-snippet-chars", type=int, default=None, help="Max chars of file snippet"
    )
    reorg.add_argument("--preview", action="store_true", help="Show Finder dialog before apply")
    reorg.add_argument(
        "--preview-cli",
        action="store_true",
        help="Interactive CLI preview (useful for long lists)",
    )
    reorg.add_argument("--plan-file", type=str, default=None, help="Write plan JSON to file")
    reorg.add_argument(
        "--open-plan", action="store_true", help="Open plan file after writing"
    )
    reorg.add_argument(
        "--open-preview", action="store_true", help="Open HTML preview diagram"
    )
    reorg.add_argument("--model", type=str, default=None, help="Ollama model override")
    reorg.add_argument("--policy", type=str, default=None, help="Policy JSON path override")
    reorg.add_argument("--context", type=str, default=None, help="Extra context for AI")
    reorg.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR fallback for non-text files (requires tesseract)",
    )
    reorg.add_argument(
        "--ocr-ask",
        action="store_true",
        help="Ask to enable OCR when text extraction fails",
    )
    reorg.set_defaults(func=cmd_reorg)

    rename = sub.add_parser("rename", help="Rename files using AI")
    rename.add_argument("paths", nargs="+", help="Target folder or file paths")
    rename.add_argument("--instruction", type=str, default=None, help="Rename instruction")
    rename.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    rename.add_argument("--recursive", action="store_true", help="Include subfolders")
    rename.add_argument("--include-hidden", action="store_true", help="Include hidden files")
    rename.add_argument("--max-files", type=int, default=None, help="Max files to process")
    rename.add_argument("--preview", action="store_true", help="Show Finder dialog before apply")
    rename.add_argument(
        "--preview-cli",
        action="store_true",
        help="Interactive CLI preview (useful for long lists)",
    )
    rename.add_argument("--plan-file", type=str, default=None, help="Write plan JSON to file")
    rename.add_argument(
        "--open-plan", action="store_true", help="Open plan file after writing"
    )
    rename.add_argument(
        "--open-preview", action="store_true", help="Open HTML preview diagram"
    )
    rename.add_argument("--model", type=str, default=None, help="Ollama model override")
    rename.add_argument("--policy", type=str, default=None, help="Policy JSON path override")
    rename.set_defaults(func=cmd_rename)

    undo = sub.add_parser("undo", help="Undo the last reorg")
    undo.add_argument("--folder", type=str, default=None, help="Folder that was reorganized")
    undo.add_argument("--id", type=str, default=None, help="Undo log id or path")
    undo.set_defaults(func=cmd_undo)

    rewrite = sub.add_parser("rewrite", help="Rewrite text to a target tone")
    rewrite.add_argument("--input", type=str, default=None, help="Input file (optional)")
    rewrite.add_argument("--tone", type=str, default=None, help="Tone description")
    rewrite.add_argument("--output", type=str, default=None, help="Output file path")
    rewrite.add_argument("--in-place", action="store_true", help="Overwrite input file")
    rewrite.add_argument("--copy", action="store_true", help="Copy output to clipboard")
    rewrite.add_argument("--model", type=str, default=None, help="Ollama model override")
    rewrite.set_defaults(func=cmd_rewrite)

    cfg = sub.add_parser("config", help="Show configuration")
    cfg.set_defaults(func=cmd_config)

    policy = sub.add_parser("policy-wizard", help="Interactive policy generator")
    policy.add_argument("--policy", type=str, default=None, help="Policy JSON path override")
    policy.set_defaults(func=cmd_policy_wizard)

    documents = sub.add_parser(
        "documents",
        help="Run the Documents folder organizer (launch agent compatible)",
    )
    documents.set_defaults(func=cmd_documents)

    coworker = sub.add_parser("coworker", help="Run coworker plans")
    coworker_sub = coworker.add_subparsers(dest="coworker_command", required=True)

    coworker_plan = coworker_sub.add_parser("plan", help="Generate a coworker plan")
    coworker_plan.add_argument("--instruction", type=str, default=None, help="LLM instruction")
    coworker_plan.add_argument(
        "--tool",
        action="append",
        default=[],
        help="Manual tool name (repeatable)",
    )
    coworker_plan.add_argument(
        "--args",
        action="append",
        default=[],
        help="Manual tool args as JSON (repeatable)",
    )
    coworker_plan.add_argument(
        "--paths",
        nargs="*",
        default=[],
        help="Selected files/folders to scope planning context",
    )
    coworker_plan.add_argument(
        "--allow-root",
        action="append",
        default=[],
        help="Additional allowed root (repeatable)",
    )
    coworker_plan.add_argument(
        "--out",
        default=None,
        help="Plan JSON output path",
    )
    coworker_plan.add_argument("--model", type=str, default=None, help="Ollama model override")
    coworker_plan.add_argument(
        "--max-snippet-chars",
        type=int,
        default=800,
        help="Max chars per text file snippet in planning prompt",
    )
    coworker_plan.set_defaults(func=cmd_coworker_plan)

    coworker_sum = coworker_sub.add_parser(
        "summarize",
        help="Generate a summary plan for selected documents",
    )
    coworker_sum.add_argument(
        "--paths",
        nargs="+",
        required=True,
        help="Files to summarize",
    )
    coworker_sum.add_argument(
        "--task",
        choices=["summary", "outline", "report"],
        default="summary",
        help="Document task to generate",
    )
    coworker_sum.add_argument("--out", default=None, help="Plan JSON output path")
    coworker_sum.add_argument("--model", type=str, default=None, help="Ollama model override")
    coworker_sum.add_argument(
        "--max-chars",
        type=int,
        default=None,
        help="Max chars per file for summary input",
    )
    coworker_sum.set_defaults(func=cmd_coworker_summarize)

    coworker_preview = coworker_sub.add_parser("preview", help="Preview a coworker plan")
    coworker_preview.add_argument("--plan", required=True, help="Plan JSON path")
    coworker_preview.add_argument(
        "--paths",
        nargs="*",
        default=[],
        help="Selected files/folders to scope access",
    )
    coworker_preview.add_argument(
        "--allow-root",
        action="append",
        default=[],
        help="Additional allowed root (repeatable)",
    )
    coworker_preview.add_argument(
        "--include-diffs",
        action="store_true",
        help="Include diffs for propose_write_file entries",
    )
    coworker_preview.set_defaults(func=cmd_coworker_preview)

    coworker_approve = coworker_sub.add_parser("approve", help="Approve a coworker plan")
    coworker_approve.add_argument("--plan", required=True, help="Plan JSON path")
    coworker_approve.add_argument(
        "--approval-file",
        default=None,
        help="Approval token output path",
    )
    coworker_approve.add_argument(
        "--checkpoint-id",
        default=None,
        help="Checkpoint id to approve (required when applying with checkpoints)",
    )
    coworker_approve.set_defaults(func=cmd_coworker_approve)

    coworker_checkpoints = coworker_sub.add_parser(
        "checkpoints",
        help="List checkpoint ids for a plan",
    )
    coworker_checkpoints.add_argument("--plan", required=True, help="Plan JSON path")
    coworker_checkpoints.set_defaults(func=cmd_coworker_checkpoints)

    coworker_apply = coworker_sub.add_parser("apply", help="Apply a coworker plan")
    coworker_apply.add_argument("--plan", required=True, help="Plan JSON path")
    coworker_apply.add_argument(
        "--approval-file",
        default=None,
        help="Approval token path (required if approvals enabled)",
    )
    coworker_apply.add_argument(
        "--resume-state",
        default=None,
        help="Resume state path from a prior checkpoint run",
    )
    coworker_apply.add_argument(
        "--checkpoint",
        action="store_true",
        help="Stop at checkpoints and write resume state",
    )
    coworker_apply.add_argument(
        "--paths",
        nargs="*",
        default=[],
        help="Selected files/folders to scope access",
    )
    coworker_apply.add_argument(
        "--allow-root",
        action="append",
        default=[],
        help="Additional allowed root (repeatable)",
    )
    coworker_apply.set_defaults(func=cmd_coworker_apply)

    coworker_rt = sub.add_parser("coworker-runtime", help="Manage coworker runtime tasks")
    coworker_rt_sub = coworker_rt.add_subparsers(dest="runtime_command", required=True)

    rt_submit = coworker_rt_sub.add_parser("submit", help="Submit a task to the runtime")
    rt_submit.add_argument("--plan", required=True, help="Plan JSON path")
    rt_submit.add_argument(
        "--bundle-root",
        default=None,
        help="Optional bundle directory (defaults under state dir)",
    )
    rt_submit.add_argument(
        "--metadata",
        default=None,
        help="Extra metadata JSON to store on the task",
    )
    rt_submit.add_argument(
        "--paths",
        nargs="*",
        default=[],
        help="Selected files/folders to scope access",
    )
    rt_submit.add_argument(
        "--allow-root",
        action="append",
        default=[],
        help="Additional allowed root (repeatable)",
    )
    rt_submit.add_argument(
        "--state-dir",
        default=None,
        help="Runtime state directory override",
    )
    rt_submit.set_defaults(func=cmd_coworker_runtime_submit)

    rt_status = coworker_rt_sub.add_parser("status", help="Show task counts by state")
    rt_status.add_argument("--state", default=None, help="Filter to a state")
    rt_status.add_argument(
        "--state-dir",
        default=None,
        help="Runtime state directory override",
    )
    rt_status.set_defaults(func=cmd_coworker_runtime_status)

    rt_list = coworker_rt_sub.add_parser("list", help="List tasks")
    rt_list.add_argument("--state", default=None, help="Filter to a state")
    rt_list.add_argument(
        "--state-dir",
        default=None,
        help="Runtime state directory override",
    )
    rt_list.set_defaults(func=cmd_coworker_runtime_list)

    rt_logs = coworker_rt_sub.add_parser("logs", help="Show task logs")
    rt_logs.add_argument("--task", required=True, help="Task id")
    rt_logs.add_argument(
        "--state-dir",
        default=None,
        help="Runtime state directory override",
    )
    rt_logs.set_defaults(func=cmd_coworker_runtime_logs)

    rt_approve = coworker_rt_sub.add_parser("approve", help="Approve a plan hash")
    rt_approve.add_argument("--plan-hash", required=True, help="Plan hash to approve")
    rt_approve.add_argument(
        "--checkpoint-id",
        default=None,
        help="Checkpoint id to approve",
    )
    rt_approve.add_argument(
        "--approved-by",
        default=None,
        help="Approval identity",
    )
    rt_approve.add_argument(
        "--state-dir",
        default=None,
        help="Runtime state directory override",
    )
    rt_approve.set_defaults(func=cmd_coworker_runtime_approve)

    rt_cancel = coworker_rt_sub.add_parser("cancel", help="Cancel a task")
    rt_cancel.add_argument("--task", required=True, help="Task id")
    rt_cancel.add_argument(
        "--state-dir",
        default=None,
        help="Runtime state directory override",
    )
    rt_cancel.set_defaults(func=cmd_coworker_runtime_cancel)

    rt_daemon = coworker_rt_sub.add_parser("daemon", help="Run runtime worker loop")
    rt_daemon.add_argument(
        "--worker-id",
        default=None,
        help="Worker identifier",
    )
    rt_daemon.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker count override",
    )
    rt_daemon.add_argument(
        "--once",
        action="store_true",
        help="Run a single iteration",
    )
    rt_daemon.add_argument(
        "--poll-seconds",
        type=float,
        default=1.0,
        help="Polling interval when idle",
    )
    rt_daemon.add_argument(
        "--state-dir",
        default=None,
        help="Runtime state directory override",
    )
    rt_daemon.set_defaults(func=cmd_coworker_runtime_daemon)

    rt_plist = coworker_rt_sub.add_parser(
        "print-plist",
        help="Print a LaunchAgent plist for the runtime daemon",
    )
    rt_plist.add_argument(
        "--label",
        default=DEFAULT_LAUNCHD_LABEL,
        help="LaunchAgent label",
    )
    rt_plist.add_argument(
        "--program",
        default=None,
        help="Path to the yordam-agent binary (defaults to PATH lookup)",
    )
    rt_plist.add_argument(
        "--state-dir",
        default=None,
        help="Runtime state directory override",
    )
    rt_plist.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker count override",
    )
    rt_plist.add_argument(
        "--poll-seconds",
        type=float,
        default=None,
        help="Polling interval when idle",
    )
    rt_plist.add_argument(
        "--worker-id",
        default=None,
        help="Worker identifier",
    )
    rt_plist.add_argument(
        "--stdout-path",
        default=None,
        help="Override StandardOutPath (defaults to /tmp)",
    )
    rt_plist.add_argument(
        "--stderr-path",
        default=None,
        help="Override StandardErrorPath (defaults to /tmp)",
    )
    rt_plist.add_argument(
        "--enable-runtime-env",
        action="store_true",
        help="Include YORDAM_COWORKER_RUNTIME_ENABLED=1 in EnvironmentVariables",
    )
    rt_plist.set_defaults(func=cmd_coworker_runtime_print_plist)

    return parser


def _default_coworker_plan_path(out_path: Optional[str], selected_paths: List[Path]) -> Path:
    if out_path:
        return Path(out_path).expanduser()
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    if selected_paths:
        root = selected_paths[0]
        root = root.parent if root.is_file() else root
    else:
        root = Path.cwd()
    return root / ".yordam-agent" / f"coworker-plan-{timestamp}.json"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
