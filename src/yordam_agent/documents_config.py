import json
from pathlib import Path
from typing import Any, Dict

from .config import CONFIG_DIR, load_config
from .util import ensure_dir

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "data" / "documents_organizer_default.json"

LEGACY_DIR = Path.home() / "Projects" / "DocumentsOrganizer"
LEGACY_CONFIG = LEGACY_DIR / "config.json"
LEGACY_CACHE = LEGACY_DIR / "hash_cache.json"

DOCS_CONFIG_FILE = CONFIG_DIR / "documents-organizer.json"
DOCS_CACHE_FILE = CONFIG_DIR / "documents-organizer-cache.json"
DOCS_LOCK_FILE = CONFIG_DIR / "documents-organizer.lock"


def documents_config_path() -> Path:
    return DOCS_CONFIG_FILE


def documents_cache_path() -> Path:
    return DOCS_CACHE_FILE


def documents_lock_path() -> Path:
    return DOCS_LOCK_FILE


def legacy_documents_config_path() -> Path:
    return LEGACY_CONFIG


def legacy_documents_cache_path() -> Path:
    return LEGACY_CACHE


def _load_default_config() -> Dict[str, Any]:
    raw = _DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


def load_documents_config() -> Dict[str, Any]:
    ensure_dir(CONFIG_DIR)
    default_config = _load_default_config()
    if DOCS_CONFIG_FILE.exists():
        current = json.loads(DOCS_CONFIG_FILE.read_text(encoding="utf-8"))
    elif LEGACY_CONFIG.exists():
        current = json.loads(LEGACY_CONFIG.read_text(encoding="utf-8"))
    else:
        current = {}

    merged = dict(default_config)
    merged.update(current)
    if not merged.get("ollama_base_url"):
        merged["ollama_base_url"] = load_config().get("ollama_base_url")

    if not DOCS_CONFIG_FILE.exists() or merged != current:
        DOCS_CONFIG_FILE.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    return merged
