import socket
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.crawlers.url_security import SafeHttpClient, UrlSecurityError, UrlSecurityPolicy


def test_url_policy_normalizes_public_https_hostname():
    policy = UrlSecurityPolicy()
    resolved = policy.resolve(
        "HTTPS://Example.COM./guide",
        resolver=lambda host, port: [(socket.AF_INET, "93.184.216.34")],
    )
    assert resolved.host == "example.com"
    assert resolved.port == 443
    assert resolved.ip_addresses == ("93.184.216.34",)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://[::1]",
        "https://example.com:8443",
        "file:///etc/passwd",
    ],
)
def test_url_policy_rejects_unsafe_targets(url):
    with pytest.raises(UrlSecurityError):
        UrlSecurityPolicy().resolve(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.2", "169.254.1.1", "::1", "fe80::1"])
def test_url_policy_rejects_private_dns_answers(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    with pytest.raises(UrlSecurityError):
        UrlSecurityPolicy().resolve(
            "https://example.com",
            resolver=lambda host, port: [(family, address)],
        )


def test_url_policy_translates_dns_failures():
    def fail(host, port):
        raise socket.gaierror("temporary DNS outage")

    with pytest.raises(UrlSecurityError, match="解析"):
        UrlSecurityPolicy().resolve("https://example.com", resolver=fail)


def test_url_policy_rejects_mixed_public_and_private_dns_answers():
    with pytest.raises(UrlSecurityError):
        UrlSecurityPolicy().resolve(
            "https://example.com",
            resolver=lambda host, port: [
                (socket.AF_INET, "93.184.216.34"),
                (socket.AF_INET, "127.0.0.1"),
            ],
        )


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            body = b"User-agent: *\nDisallow: /\nAllow: /final\nAllow: /redirect\nAllow: /journal*\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/final")
            self.end_headers()
            return
        body = b"<html><title>Fixture</title><body>safe</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def test_safe_client_follows_allowed_redirects_and_limits_content():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = SafeHttpClient(allow_local_http=True, max_bytes=16)
        with pytest.raises(UrlSecurityError, match="页面超过大小限制"):
            client.get(f"http://127.0.0.1:{server.server_port}/final")
        client = SafeHttpClient(allow_local_http=True, max_bytes=1024)
        result = client.get(f"http://127.0.0.1:{server.server_port}/redirect")
        assert result.status == 200
        assert result.final_url.endswith("/final")
        assert len(result.redirects) == 1
        assert "safe" in result.text
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_safe_client_posts_json_without_sending_credentials_to_redirects():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = SafeHttpClient(allow_local_http=True)
        result = client.post_json(
            f"http://127.0.0.1:{server.server_port}/search",
            {"text_query": "Journal One"},
            headers={"Authorization": "Bearer secret"},
        )
        assert result.status == 200
        assert result.text == '{"text_query": "Journal One"}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_safe_client_honors_robots_txt_rules():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = SafeHttpClient(allow_local_http=True)
        with pytest.raises(UrlSecurityError, match="robots"):
            client.get(f"http://127.0.0.1:{server.server_port}/private")
        result = client.get(f"http://127.0.0.1:{server.server_port}/final")
        assert result.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_robots_specific_allow_rule_wins_over_global_disallow():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = SafeHttpClient(allow_local_http=True)
        result = client.get(f"http://127.0.0.1:{server.server_port}/journal/40313")
        assert result.status == 200
        robots = client.get(f"http://127.0.0.1:{server.server_port}/robots.txt")
        assert robots.status == 200
        with pytest.raises(UrlSecurityError, match="robots"):
            client.get(f"http://127.0.0.1:{server.server_port}/private")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_safe_client_rate_limits_requests_to_same_host():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import time
        client = SafeHttpClient(allow_local_http=True, min_interval_seconds=0.05)
        started = time.monotonic()
        for _ in range(2):
            client.get(f"http://127.0.0.1:{server.server_port}/final")
        assert time.monotonic() - started >= 0.04
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_default_client_rejects_local_http_before_connecting():
    with pytest.raises(UrlSecurityError):
        SafeHttpClient().get("http://127.0.0.1:8000/admin")
