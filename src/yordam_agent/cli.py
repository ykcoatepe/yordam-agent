import argparse
import sys
from datetime import datetime
from pathlib import Path
import subprocess
from typing import Dict, List, Optional

from .ai_log import resolve_log_path
from .config import config_path, load_config
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
    buttons = "\"Cancel\", \"Save Plan\", \"Apply\"" if allow_apply else "\"Cancel\", \"Save Plan\", \"OK\""
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
    log_path = resolve_log_path(cfg.get("ai_log_path"), root)
    client = OllamaClient(
        cfg["ollama_base_url"],
        log_path=log_path,
        log_include_response=bool(cfg.get("ai_log_include_response")),
    )
    model = args.model or cfg["model"]
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
    model = args.model or cfg["rewrite_model"]
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
    client = OllamaClient(
        cfg["ollama_base_url"],
        log_path=log_path,
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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
