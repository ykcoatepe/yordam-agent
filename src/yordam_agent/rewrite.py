from typing import Any, Dict, Optional

from .ollama import OllamaClient


def rewrite_text(
    text: str,
    tone: str,
    client: OllamaClient,
    model: str,
    log_context: Optional[Dict[str, Any]] = None,
) -> str:
    system = (
        "You are a writing assistant. Rewrite the text in the requested tone. "
        "Preserve meaning and keep formatting (line breaks, lists) when possible. "
        "Return only the rewritten text."
    )
    prompt = f"Tone: {tone}\n\nText:\n{text}"
    return client.generate(
        model=model,
        prompt=prompt,
        system=system,
        temperature=0.4,
        log_context=log_context,
    )


def derive_output_path(input_path: str) -> str:
    if "." in input_path:
        parts = input_path.rsplit(".", 1)
        return f"{parts[0]}.rewrite.{parts[1]}"
    return f"{input_path}.rewrite"


def normalize_tone(tone: Optional[str]) -> str:
    return tone.strip() if tone else "clear, friendly, professional"
