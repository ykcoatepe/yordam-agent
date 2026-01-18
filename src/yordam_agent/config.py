import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path.home() / ".config" / "yordam-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "ollama_base_url": "http://localhost:11434",
    "model": "gpt-oss:20b",
    "model_secondary": "gpt-oss:20b",
    "gpt_oss_think_level": "low",
    "available_models": [
        "qwen3-vl:30b",
        "deepseek-r1:8b",
        "glm-4.6:cloud",
        "minimax-m2:cloud",
        "gpt-oss:20b",
        "gpt-oss:20b-instruct",
        "gpt-oss:120b-instruct",
        "gpt-oss:120b",
    ],
    "reasoning_level_models": [
        "gpt-oss",
        "gpt-oss:latest",
        "gpt-oss:20b",
        "gpt-oss:120b",
    ],
    "rewrite_model": "gpt-oss:20b",
    "rewrite_model_secondary": "gpt-oss:20b",
    "max_snippet_chars": 4000,
    "max_files": 200,
    "policy_path": str(CONFIG_DIR / "policy.json"),
    "ai_log_path": ".yordam-agent/ai-interactions.jsonl",
    "ai_log_include_response": False,
    "reorg_context": "",
    "ocr_enabled": False,
    "ocr_prompt": True,
    "coworker_allowed_paths": [],
    "coworker_require_approval": True,
    "coworker_max_read_bytes": 200000,
    "coworker_max_write_bytes": 200000,
    "coworker_web_enabled": False,
    "coworker_web_allowlist": [],
    "coworker_web_max_bytes": 200000,
    "coworker_web_max_query_chars": 256,
    "coworker_checkpoint_every_writes": 5,
    "coworker_ocr_enabled": False,
    "coworker_ocr_prompt": True,
}

ENV_OVERRIDES = {
    "YORDAM_OLLAMA_BASE_URL": "ollama_base_url",
    "YORDAM_MODEL": "model",
    "YORDAM_MODEL_SECONDARY": "model_secondary",
    "YORDAM_GPT_OSS_THINK_LEVEL": "gpt_oss_think_level",
    "YORDAM_REWRITE_MODEL": "rewrite_model",
    "YORDAM_REWRITE_MODEL_SECONDARY": "rewrite_model_secondary",
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
