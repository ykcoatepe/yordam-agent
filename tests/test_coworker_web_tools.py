import contextlib
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker.web_tools import fetch_url, sanitize_html  # noqa: E402


@contextlib.contextmanager
def run_server(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


class _BaseHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return


class RedirectSameHostHandler(_BaseHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/final")
            self.end_headers()
            return
        if self.path == "/final":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


class RedirectDisallowedHostHandler(_BaseHandler):
    def do_GET(self):
        if self.path == "/redirect":
            port = self.server.server_address[1]
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{port}/final")
            self.end_headers()
            return
        if self.path == "/final":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


class RedirectQueryHandler(_BaseHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/final?token=abc")
            self.end_headers()
            return
        if self.path.startswith("/final"):
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


class TestFetchUrlRedirects(unittest.TestCase):
    def test_fetch_url_allows_redirect_to_allowlisted_host(self) -> None:
        with run_server(RedirectSameHostHandler) as server:
            url = f"http://127.0.0.1:{server.server_address[1]}/redirect"
            body, content_type = fetch_url(url, max_bytes=32, allowlist=["127.0.0.1"])
            self.assertEqual(body, "ok")
            self.assertEqual(content_type, "text/plain")

    def test_fetch_url_blocks_redirect_to_disallowed_host(self) -> None:
        with run_server(RedirectDisallowedHostHandler) as server:
            url = f"http://localhost:{server.server_address[1]}/redirect"
            with self.assertRaises(RuntimeError) as ctx:
                fetch_url(url, max_bytes=32, allowlist=["localhost"])
            self.assertIn("redirect", str(ctx.exception).lower())

    def test_fetch_url_blocks_redirect_query_without_allow(self) -> None:
        with run_server(RedirectQueryHandler) as server:
            url = f"http://127.0.0.1:{server.server_address[1]}/redirect"
            with self.assertRaises(RuntimeError) as ctx:
                fetch_url(
                    url,
                    max_bytes=32,
                    allowlist=["127.0.0.1"],
                    allow_query=False,
                    max_query_chars=10,
                )
            self.assertIn("query", str(ctx.exception).lower())

    def test_fetch_url_allows_redirect_query_when_allowed(self) -> None:
        with run_server(RedirectQueryHandler) as server:
            url = f"http://127.0.0.1:{server.server_address[1]}/redirect"
            body, content_type = fetch_url(
                url,
                max_bytes=32,
                allowlist=["127.0.0.1"],
                allow_query=True,
                max_query_chars=32,
            )
            self.assertEqual(body, "ok")
            self.assertEqual(content_type, "text/plain")

class TestSanitizeHtml(unittest.TestCase):
    def test_sanitize_html_strips_script_and_style_contents(self) -> None:
        raw = (
            "<html><body>Hi"
            "<script>console.log('x')</script>"
            "<style>body{color:red}</style>"
            "there</body></html>"
        )
        cleaned = sanitize_html(raw)
        self.assertEqual(cleaned, "Hi there")
