import hashlib
import ipaddress
import json
import re
import socket
import ssl
import time
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from threading import Lock
from urllib import robotparser
from urllib.parse import unquote, urljoin, urlsplit


class UrlSecurityError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedUrl:
    url: str
    host: str
    port: int
    ip_addresses: tuple[str, ...]
    scheme: str


@dataclass(frozen=True)
class FetchResult:
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    text: str
    redirects: tuple[str, ...]
    content_sha256: str


def _default_resolver(host: str, port: int) -> list[tuple[int, str]]:
    return [
        (int(item[0]), str(item[4][0]))
        for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ]


def _rule_matches(pattern: str, path: str) -> bool:
    if not pattern:
        return False
    exact_end = pattern.endswith("$")
    raw_pattern = pattern[:-1] if exact_end else pattern
    expression = re.escape(raw_pattern).replace(r"\*", ".*")
    if exact_end:
        return re.fullmatch(expression, path) is not None
    return re.match(expression, path) is not None


def _can_fetch_robots(parser: robotparser.RobotFileParser, user_agent: str, url: str) -> bool:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    agent_name = user_agent.split("/", maxsplit=1)[0].lower()
    specific_entries = [
        entry
        for entry in getattr(parser, "entries", [])
        if any(agent.lower() in agent_name for agent in entry.useragents)
    ]
    if specific_entries:
        entries = specific_entries
    else:
        entries = [getattr(parser, "default_entry")] if getattr(parser, "default_entry", None) is not None else []
    matches = []
    for entry in entries:
        for rule in entry.rulelines:
            rule_path = unquote(rule.path)
            if _rule_matches(rule_path, path):
                specificity = len(rule_path.replace("*", "").replace("$", ""))
                matches.append((specificity, rule.allowance))
    if not matches:
        return True
    most_specific = max(specificity for specificity, allowance in matches)
    return any(
        allowance
        for specificity, allowance in matches
        if specificity == most_specific and allowance
    )


class UrlSecurityPolicy:
    def __init__(self, *, allow_local_http: bool = False):
        self.allow_local_http = allow_local_http

    def resolve(self, url: str, *, resolver=None) -> ResolvedUrl:
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port
        except ValueError as exc:
            raise UrlSecurityError("URL 格式无效") from exc
        if parsed.username is not None or parsed.password is not None or not host:
            raise UrlSecurityError("URL 不得包含凭据且必须包含主机名")
        if "%" in host:
            raise UrlSecurityError("URL 主机名无效")
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise UrlSecurityError("URL 主机名无效") from exc
        local_http = self.allow_local_http and parsed.scheme == "http" and host in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if parsed.scheme != "https" and not local_http:
            raise UrlSecurityError("仅允许访问 HTTPS 公开网站")
        if not local_http and port not in (None, 443):
            raise UrlSecurityError("仅允许访问默认 HTTPS 端口")
        effective_port = port or (80 if local_http else 443)
        try:
            answers = (resolver or _default_resolver)(host, effective_port)
        except socket.gaierror as exc:
            raise UrlSecurityError("目标主机解析失败") from exc
        addresses = tuple(dict.fromkeys(address for family, address in answers))
        if not addresses:
            raise UrlSecurityError("无法解析目标主机")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not local_http and not ip.is_global:
                raise UrlSecurityError("目标地址属于禁止访问的网络范围")
        return ResolvedUrl(
            url=url,
            host=host,
            port=effective_port,
            ip_addresses=addresses,
            scheme="http" if local_http else "https",
        )


class _PinnedHTTPConnection(HTTPConnection):
    def __init__(self, host: str, ip_address: str, port: int, timeout: float):
        super().__init__(host, port=port, timeout=timeout)
        self._ip_address = ip_address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._ip_address, self.port), self.timeout)


class _PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, host: str, ip_address: str, port: int, timeout: float):
        context = ssl.create_default_context()
        super().__init__(host, port=port, timeout=timeout, context=context)
        self._ip_address = ip_address
        self._ssl_context = context

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._ip_address, self.port), self.timeout)
        self.sock = self._ssl_context.wrap_socket(raw_socket, server_hostname=self.host)


class SafeHttpClient:
    def __init__(
        self,
        *,
        allow_local_http: bool = False,
        timeout: float = 15.0,
        max_bytes: int = 2_000_000,
        max_redirects: int = 5,
        min_interval_seconds: float = 0.2,
    ):
        self.policy = UrlSecurityPolicy(allow_local_http=allow_local_http)
        self.allow_local_http = allow_local_http
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.min_interval_seconds = min_interval_seconds
        self._rate_lock = Lock()
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}

    def _throttle(self, host: str) -> None:
        with self._rate_lock:
            now = time.monotonic()
            wait = self.min_interval_seconds - (now - self._last_request.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self._last_request[host] = time.monotonic()

    def assert_allowed(self, url: str) -> None:
        resolved = self.policy.resolve(url)
        if urlsplit(url).path == "/robots.txt":
            return
        origin = f"{resolved.scheme}://{resolved.host}:{resolved.port}"
        if origin not in self._robots:
            robots_url = f"{origin}/robots.txt"
            result = self._get_once(self.policy.resolve(robots_url))
            if result.status == 404:
                self._robots[origin] = None
            elif result.status == 200:
                parser = robotparser.RobotFileParser()
                parser.parse(result.text.splitlines())
                self._robots[origin] = parser
            elif result.status in {401, 403}:
                parser = robotparser.RobotFileParser()
                parser.parse(["User-agent: *", "Disallow: /"])
                self._robots[origin] = parser
            else:
                raise UrlSecurityError("robots 规则获取失败")
        rules = self._robots[origin]
        if rules is not None and not _can_fetch_robots(
            rules, "AcademicSubmissionAgent/0.1 JournalDiscovery", url
        ):
            raise UrlSecurityError("robots 规则禁止访问该路径")

    def get(self, url: str) -> FetchResult:
        redirects: list[str] = []
        current_url = url
        while True:
            resolved = self.policy.resolve(current_url)
            self.assert_allowed(current_url)
            result = self._get_once(resolved)
            if result.status not in {301, 302, 303, 307, 308}:
                return FetchResult(
                    final_url=current_url,
                    status=result.status,
                    headers=result.headers,
                    body=result.body,
                    text=result.text,
                    redirects=tuple(redirects),
                    content_sha256=hashlib.sha256(result.body).hexdigest(),
                )
            location = result.headers.get("location")
            if not location:
                raise UrlSecurityError("重定向缺少目标地址")
            if len(redirects) >= self.max_redirects:
                raise UrlSecurityError("重定向次数超过限制")
            current_url = urljoin(current_url, location)
            redirects.append(current_url)

    def post_json(
        self,
        url: str,
        payload: dict,
        *,
        headers: dict[str, str] | None = None,
    ) -> FetchResult:
        resolved = self.policy.resolve(url)
        result = self._get_once(
            resolved,
            method="POST",
            payload=json.dumps(payload).encode("utf-8"),
            extra_headers=headers,
        )
        if result.status in {301, 302, 303, 307, 308}:
            raise UrlSecurityError("带凭据的请求不得跟随重定向")
        return FetchResult(
            final_url=resolved.url,
            status=result.status,
            headers=result.headers,
            body=result.body,
            text=result.text,
            redirects=(),
            content_sha256=hashlib.sha256(result.body).hexdigest(),
        )

    def _get_once(
        self,
        resolved: ResolvedUrl,
        *,
        method: str = "GET",
        payload: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> FetchResult:
        self._throttle(resolved.host)
        connection_class = _PinnedHTTPConnection if resolved.scheme == "http" else _PinnedHTTPSConnection
        connection = connection_class(
            resolved.host,
            resolved.ip_addresses[0],
            resolved.port,
            self.timeout,
        )
        parsed = urlsplit(resolved.url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        default_port = 80 if resolved.scheme == "http" else 443
        host_header = resolved.host if resolved.port == default_port else f"{resolved.host}:{resolved.port}"
        request_headers = {
            "Host": host_header,
            "User-Agent": "AcademicSubmissionAgent/0.1 JournalDiscovery",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if extra_headers:
            request_headers.update(extra_headers)
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(payload))
        try:
            connection.request(method, path, body=payload, headers=request_headers)
            response = connection.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise UrlSecurityError("页面超过大小限制")
            content_type = headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
            allowed_types = {
                "text/html",
                "application/xhtml+xml",
                "application/json",
                "text/plain",
                "",
            }
            if content_type not in allowed_types:
                raise UrlSecurityError("目标内容类型不受支持")
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                text = body.decode(charset, errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")
            return FetchResult(
                final_url=resolved.url,
                status=response.status,
                headers=headers,
                body=body,
                text=text,
                redirects=(),
                content_sha256="",
            )
        except UrlSecurityError:
            raise
        except (OSError, socket.timeout, ssl.SSLError) as exc:
            raise UrlSecurityError("目标网站访问失败") from exc
        finally:
            connection.close()
