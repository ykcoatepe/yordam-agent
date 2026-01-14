import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path.home() / ".config" / "yordam-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "ollama_base_url": "http://localhost:11434",
    "model": "gpt-oss:20b",
    "rewrite_model": "gpt-oss:20b-instruct",
    "max_snippet_chars": 4000,
    "max_files": 200,
    "policy_path": str(CONFIG_DIR / "policy.json"),
    "ai_log_path": ".yordam-agent/ai-interactions.jsonl",
}

ENV_OVERRIDES = {
    "YORDAM_OLLAMA_BASE_URL": "ollama_base_url",
    "YORDAM_MODEL": "model",
    "YORDAM_REWRITE_MODEL": "rewrite_model",
    "YORDAM_AI_LOG_PATH": "ai_log_path",
}


def _apply_env_overrides(cfg: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(cfg)
    for env_key, cfg_key in ENV_OVERRIDES.items():
        value = os.environ.get(env_key)
        if value:
            updated[cfg_key] = value
    return updated


def load_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    if merged != cfg:
        CONFIG_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return _apply_env_overrides(merged)


def config_path() -> Path:
    return CONFIG_FILE
