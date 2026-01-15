import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.ollama import OllamaClient  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload.encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class OllamaFallbackTests(unittest.TestCase):
    def test_generate_uses_fallback_model(self) -> None:
        client = OllamaClient("http://localhost:11434", fallback_model="gpt-oss:20b")
        with mock.patch("yordam_agent.ollama.urllib.request.urlopen") as mocked:
            mocked.side_effect = [
                urllib.error.URLError("boom"),
                _FakeResponse('{"response": "ok"}'),
            ]
            result = client.generate(model="deepseek-r1:8b", prompt="hi")
            self.assertEqual(result, "ok")
            self.assertEqual(mocked.call_count, 2)


if __name__ == "__main__":
    unittest.main()
