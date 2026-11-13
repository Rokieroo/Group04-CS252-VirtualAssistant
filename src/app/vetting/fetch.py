"""Fetch untrusted web pages safely (spec 11.3 step 1 and 13.2).

Every hop is checked before it is contacted: http(s) only, not blocklisted,
allowed by ``robots.txt``, and every address the host resolves to is public.
The connection then goes to the address that was checked (the hostname rides
along in ``Host`` and SNI), so DNS rebinding cannot swap in a private address
between the check and the connect.  At most 3 redirects, 10 seconds and 5 MB
per page; no cookies, no proxies from the environment, no JavaScript.
"""

from __future__ import annotations

import codecs
import ipaddress
import re
import socket
import ssl
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Self
from urllib.robotparser import RobotFileParser

import httpx
import truststore

from app.vetting.policy import DomainPolicy, DomainTier, default_policy

__all__ = [
    "DomainThrottle",
    "FetchError",
    "FetchResult",
    "RateBudgetExceeded",
    "SafeFetcher",
    "pinned_client",
    "public_address",
    "safe_fetch",
    "send_pinned",
]

USER_AGENT = "PathlyBot/1.0 (+https://github.com/Rokieroo/Group04-CS252-VirtualAssistant)"
# urllib.robotparser matches agents by substring: a token like "PathlyFetcher"
# would obey Wikipedia's "User-agent: Fetch / Disallow: /" and lose every page.
ROBOTS_AGENT = "PathlyBot"
TIMEOUT = 10.0
MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
ROBOTS_MAX_BYTES = 512 * 1024
ROBOTS_TTL = 24 * 3600  # RFC 9309 caps robots.txt caching at 24 hours
ROBOTS_CACHE_SIZE = 4096
_SCHEMES = ("http", "https")
_REDIRECTS = {301, 302, 303, 307, 308}
_AUTH_STATUSES = {401, 402, 403}
_PASSWORD_INPUT = re.compile(r"<input\b[^>]*\btype\s*=\s*[\"']?password\b", re.IGNORECASE)
_LOGIN_PATH = re.compile(
    r"/(?:log-?in|sign-?in|dang-?nhap|auth|sso)\b", re.IGNORECASE
)

Resolver = Callable[[str, int], list[str]]


class FetchError(Exception):
    """A fetch refused or failed; ``reason`` is a short, log-safe code."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def public_address(url: httpx.URL, resolver: Resolver = resolve) -> str:
    """The address to connect to, if ``url`` is http(s) and its host is wholly public.

    Every resolved address must be public, not just the first: a host that also
    answers with a private address is refused outright.
    """
    if url.scheme not in _SCHEMES or not url.raw_host:
        raise FetchError("bad_scheme")
    try:
        addresses = resolver(url.raw_host.decode("ascii"), url.port or (
            443 if url.scheme == "https" else 80))
    except (OSError, UnicodeError) as exc:
        raise FetchError("dns") from exc
    if not addresses:
        raise FetchError("dns")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError as exc:
            raise FetchError("private_address") from exc
        if not ip.is_global or ip.is_multicast:
            raise FetchError("private_address")
    return addresses[0].split("%", 1)[0]


def pinned_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """A client fit for :func:`send_pinned`.

    No keep-alive: pooled connections are keyed by address, so a reused one
    could carry another hostname's TLS session.  ``trust_env=False`` keeps
    proxies and ``.netrc`` credentials out of requests to arbitrary sites.
    """
    return httpx.Client(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        limits=httpx.Limits(max_keepalive_connections=0),
        # OS trust store, as in app.llm.gemini: TLS inspection breaks certifi.
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )


def send_pinned(
    client: httpx.Client,
    method: str,
    url: httpx.URL,
    *,
    timeout: float,
    address: str | None = None,
    user_agent: str = USER_AGENT,
) -> httpx.Response:
    """Send one request to the checked address of ``url``; the caller closes the response.

    ``address`` must come from :func:`public_address`; it is looked up when omitted.
    The request is built by hand, so the client's cookie jar is never sent.
    """
    address = address or public_address(url)
    request = httpx.Request(
        method,
        url.copy_with(host=address, userinfo=b""),
        headers={"Host": url.netloc.decode("ascii"), "User-Agent": user_agent},
        extensions={
            "timeout": httpx.Timeout(timeout).as_dict(),
            "sni_hostname": url.raw_host.decode("ascii"),
        },
    )
    return client.send(request, stream=True)


class RateBudgetExceeded(Exception):
    """A domain used up its hourly request budget. It says nothing about any page,
    so ``SafeFetcher.fetch`` lets it reach the caller instead of returning it."""

    def __init__(self, domain: str):
        super().__init__(domain)
        self.domain = domain


class DomainThrottle:
    """Spaces requests to each host by the rate of the domain that owns it.

    ``rates`` maps a domain to requests per second (``rate_limit_per_sec`` in
    ADR 004); hosts under no listed domain get ``default`` (1 req/s when a
    provider publishes no limit). Waits count toward a page's timeout. With
    ``per_hour``, a request that would make more than that many on one domain
    within an hour raises :class:`RateBudgetExceeded` instead of waiting.
    """

    def __init__(
        self,
        rates: dict[str, float] | None = None,
        *,
        default: float = 1.0,
        per_hour: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.rates = {d.lower().strip("."): r for d, r in (rates or {}).items()}
        self.default = default
        self.per_hour = per_hour
        self.clock = clock
        self.sleep = sleep
        self._next: dict[str, float] = {}
        self._sent: dict[str, deque[float]] = {}  # domain -> request times, oldest first
        self._lock = threading.Lock()

    def _domain(self, host: str) -> str:
        """The listed domain that owns ``host``, else the host itself."""
        host = host.lower().rstrip(".")
        return next((d for d in self.rates if host == d or host.endswith("." + d)), host)

    def interval(self, host: str) -> float:
        return 1.0 / self.rates.get(self._domain(host), self.default)

    def wait(self, host: str) -> None:
        host_key = host.lower().rstrip(".")
        with self._lock:
            now = self.clock()
            if self.per_hour is not None:
                domain = self._domain(host_key)
                sent = self._sent.setdefault(domain, deque())
                while sent and sent[0] <= now - 3600:
                    sent.popleft()
                if len(sent) >= self.per_hour:
                    raise RateBudgetExceeded(domain)
                sent.append(now)
            start = max(now, self._next.get(host_key, now))
            self._next[host_key] = start + self.interval(host_key)
        if start > now:
            self.sleep(start - now)


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str = ""
    status: int | None = None
    content_type: str = ""
    body: bytes = b""
    encoding: str = "utf-8"
    error: str | None = None
    paywall: str | None = None

    @property
    def ok(self) -> bool:
        """Passes spec 11.3 step 1: a readable 200 that is not a login or paywall."""
        return self.error is None and self.status == 200 and self.paywall is None

    @property
    def content_hash(self) -> str:
        return sha256(self.body).hexdigest()

    @property
    def text(self) -> str:
        return self.body.decode(self.encoding, errors="replace")


def _encoding(response: httpx.Response) -> str:
    name = response.charset_encoding or "utf-8"
    try:
        return codecs.lookup(name).name
    except LookupError:
        return "utf-8"


class SafeFetcher:
    """Reusable fetcher; keep one per job so ``robots.txt`` answers are cached.

    ``resolver`` and ``transport`` exist for tests; production uses DNS and the
    network. ``throttle`` spaces every request, ``robots.txt`` included.
    """

    def __init__(
        self,
        *,
        timeout: float = TIMEOUT,
        max_bytes: int = MAX_BYTES,
        max_redirects: int = MAX_REDIRECTS,
        policy: DomainPolicy | None = None,
        resolver: Resolver = resolve,
        transport: httpx.BaseTransport | None = None,
        respect_robots: bool = True,
        throttle: DomainThrottle | None = None,
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.policy = policy or default_policy()
        self.resolver = resolver
        self.respect_robots = respect_robots
        self.throttle = throttle
        self._client = pinned_client(transport)
        self._robots: dict[str, tuple[float, RobotFileParser]] = {}
        self._robots_lock = threading.Lock()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch(self, url: str) -> FetchResult:
        """Never raises for the page's sake: refusals land in ``FetchResult.error``."""
        deadline = time.monotonic() + self.timeout
        try:
            requested = httpx.URL(url)
            final, response, body = self._get(
                requested, deadline, self.max_bytes, check_robots=self.respect_robots
            )
        except (FetchError, httpx.InvalidURL) as exc:
            reason = exc.reason if isinstance(exc, FetchError) else "invalid_url"
            return FetchResult(url=url, error=reason)
        result = FetchResult(
            url=url,
            final_url=str(final),
            status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            body=body,
            encoding=_encoding(response),
        )
        paywall = self._paywall(requested, final, result)
        return result if paywall is None else replace(result, paywall=paywall)

    def _get(
        self, target: httpx.URL, deadline: float, max_bytes: int, *, check_robots: bool
    ) -> tuple[httpx.URL, httpx.Response, bytes]:
        for _hop in range(self.max_redirects + 1):
            # Every hop is re-checked: a safe page may redirect anywhere.
            if target.scheme not in _SCHEMES:
                raise FetchError("bad_scheme")
            # Policy first: a blocked host is not even looked up.
            if self.policy.tier(str(target)) is DomainTier.BLOCKED:
                raise FetchError("blocked_domain")
            address = public_address(target, self.resolver)
            if check_robots and not self._robots_allow(target, deadline):
                raise FetchError("robots")
            response = self._send(target, address, deadline)
            location = response.headers.get("location")
            if response.status_code in _REDIRECTS and location:
                response.close()
                target = target.join(location)
                continue
            try:
                return target, response, self._read(response, deadline, max_bytes)
            finally:
                response.close()
        raise FetchError("too_many_redirects")

    def _send(self, target: httpx.URL, address: str, deadline: float) -> httpx.Response:
        if self.throttle is not None:
            self.throttle.wait(target.raw_host.decode("ascii"))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError("timeout")
        try:
            return send_pinned(self._client, "GET", target, timeout=remaining, address=address)
        except httpx.TimeoutException as exc:
            raise FetchError("timeout") from exc
        except httpx.HTTPError as exc:
            raise FetchError("network") from exc

    @staticmethod
    def _read(response: httpx.Response, deadline: float, max_bytes: int) -> bytes:
        length = response.headers.get("content-length", "")
        if length.isdigit() and int(length) > max_bytes:
            raise FetchError("too_large")
        chunks: list[bytes] = []
        size = 0
        try:
            # Decoded bytes are counted, so a gzip bomb hits the limit too.
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise FetchError("too_large")
                if time.monotonic() > deadline:
                    raise FetchError("timeout")
                chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise FetchError("timeout") from exc
        except httpx.HTTPError as exc:
            raise FetchError("network") from exc
        return b"".join(chunks)

    def _robots_allow(self, target: httpx.URL, deadline: float) -> bool:
        origin = f"{target.scheme}://{target.netloc.decode('ascii')}"
        now = time.monotonic()
        with self._robots_lock:
            cached = self._robots.get(origin)
        if cached is None or cached[0] < now:
            rules, cacheable = self._load_robots(origin, deadline)
            if cacheable:
                with self._robots_lock:
                    if len(self._robots) >= ROBOTS_CACHE_SIZE:
                        # shortcut: drops the whole cache when full; use an LRU if hit rates suffer.
                        self._robots.clear()
                    self._robots[origin] = (now + ROBOTS_TTL, rules)
        else:
            rules = cached[1]
        return rules.can_fetch(ROBOTS_AGENT, str(target))

    def _load_robots(self, origin: str, deadline: float) -> tuple[RobotFileParser, bool]:
        """RFC 9309: 4xx allows everything; an unreachable file allows nothing.

        Unreachable answers are not cached, so a blip costs one page, not a day.
        """
        rules = RobotFileParser()
        try:
            _final, response, body = self._get(
                httpx.URL(origin + "/robots.txt"), deadline, ROBOTS_MAX_BYTES,
                check_robots=False,
            )
        except FetchError:
            rules.disallow_all = True
            return rules, False
        if response.status_code >= 500:
            rules.disallow_all = True
            return rules, False
        if response.status_code >= 400:
            rules.allow_all = True
        else:
            rules.parse(body.decode("utf-8", errors="replace").splitlines())
        return rules, True

    def _paywall(self, requested: httpx.URL, final: httpx.URL, result: FetchResult) -> str | None:
        """Rule-based login/paywall detection (spec 11.3 step 1)."""
        if result.status in _AUTH_STATUSES:
            return f"http_{result.status}"
        if self.policy.is_paywalled(result.final_url):
            return "known_domain"
        if final != requested and _LOGIN_PATH.search(final.path):
            return "login_redirect"
        if "html" in result.content_type.casefold() and _PASSWORD_INPUT.search(result.text):
            return "login_form"
        return None


def safe_fetch(url: str, **options) -> FetchResult:
    """One-off fetch; batch callers should share a :class:`SafeFetcher`."""
    with SafeFetcher(**options) as fetcher:
        return fetcher.fetch(url)
