import html
import re
import urllib.error
import urllib.request
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse


def fetch_url(
    url: str,
    *,
    max_bytes: int,
    allowlist: Iterable[str],
    timeout: float = 15.0,
) -> Tuple[str, str]:
    if max_bytes <= 0:
        raise RuntimeError("web.fetch max_bytes must be positive")
    allowlist_entries = tuple(str(entry) for entry in allowlist)
    if not allowlist_entries:
        raise RuntimeError("web.fetch allowlist must be provided")
    _ensure_allowed_url(url, allowlist_entries, context="url")
    req = urllib.request.Request(url, method="GET")
    try:
        opener = urllib.request.build_opener(_AllowlistRedirectHandler(allowlist_entries))
        with opener.open(req, timeout=timeout) as resp:
            _ensure_allowed_url(resp.geturl(), allowlist_entries, context="redirect")
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(max_bytes + 1)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"web.fetch failed: {exc}") from exc
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    text = _decode_body(raw, content_type)
    if _is_html(content_type, text):
        text = sanitize_html(text)
    return text, content_type


def sanitize_html(value: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _decode_body(raw: bytes, content_type: str) -> str:
    charset = _extract_charset(content_type) or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _extract_charset(content_type: str) -> Optional[str]:
    match = re.search(r"charset=([A-Za-z0-9_\\-]+)", content_type, re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _is_html(content_type: str, text: str) -> bool:
    if "text/html" in content_type.lower():
        return True
    return "<html" in text.lower() or "<body" in text.lower()


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowlist: Iterable[str]) -> None:
        super().__init__()
        self._allowlist = tuple(allowlist)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            _ensure_allowed_url(newurl, self._allowlist, context="redirect")
        except urllib.error.URLError:
            if fp is not None:
                fp.close()
            raise
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ensure_allowed_url(url: str, allowlist: Iterable[str], *, context: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise urllib.error.URLError(f"{context} blocked to unsupported scheme: {parsed.scheme}")
    host = parsed.hostname or ""
    if not _host_allowed(host, allowlist):
        raise urllib.error.URLError(f"{context} blocked to disallowed host: {host}")


def _host_allowed(host: str, allowlist: Iterable[str]) -> bool:
    host = host.lower()
    for entry in allowlist:
        candidate = str(entry).lower()
        if host == candidate or host.endswith(f".{candidate}"):
            return True
    return False
