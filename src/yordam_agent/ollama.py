import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from .ai_log import append_ai_log, build_log_entry


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        log_path: Optional[Path] = None,
        *,
        log_include_response: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.log_path = log_path
        self.log_include_response = log_include_response

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        log_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.perf_counter()
        response_text = ""
        error_type: Optional[str] = None
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            error_type = type(exc).__name__
            self._log_interaction(
                model=model,
                temperature=temperature,
                prompt=prompt,
                system=system,
                response_text=response_text,
                start=start,
                error_type=error_type,
                context=log_context,
            )
            raise RuntimeError(f"Ollama request failed: {exc}") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            error_type = type(exc).__name__
            self._log_interaction(
                model=model,
                temperature=temperature,
                prompt=prompt,
                system=system,
                response_text=response_text,
                start=start,
                error_type=error_type,
                context=log_context,
            )
            raise RuntimeError("Ollama returned invalid JSON") from exc
        if "response" not in parsed:
            error_type = "MissingResponseField"
            self._log_interaction(
                model=model,
                temperature=temperature,
                prompt=prompt,
                system=system,
                response_text=response_text,
                start=start,
                error_type=error_type,
                context=log_context,
            )
            raise RuntimeError("Ollama response missing 'response' field")
        response_text = str(parsed["response"])
        self._log_interaction(
            model=model,
            temperature=temperature,
            prompt=prompt,
            system=system,
            response_text=response_text,
            start=start,
            error_type=None,
            context=log_context,
        )
        return response_text

    def _log_interaction(
        self,
        *,
        model: str,
        temperature: Optional[float],
        prompt: str,
        system: Optional[str],
        response_text: str,
        start: float,
        error_type: Optional[str],
        context: Optional[Dict[str, Any]],
    ) -> None:
        if not self.log_path:
            return
        duration_ms = int((time.perf_counter() - start) * 1000)
        entry = build_log_entry(
            model=model,
            temperature=temperature,
            prompt_chars=len(prompt),
            system_chars=len(system) if system else 0,
            response_chars=len(response_text),
            duration_ms=duration_ms,
            success=error_type is None,
            error_type=error_type,
            context=context,
            response_text=response_text,
            include_response=self.log_include_response,
        )
        append_ai_log(self.log_path, entry)
