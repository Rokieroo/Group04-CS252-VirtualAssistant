"""Is a resource link still alive? (spec 11.7)

Only public http(s) addresses are contacted, redirects are not followed and no
body is downloaded: the daily check needs a status code, not the page.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

USER_AGENT = (
    "PathlyLinkCheck/1.0 "
    "(+https://github.com/Rokieroo/Group04-CS252-VirtualAssistant)"
)
# Sites that block bots or rate-limit say nothing about the link itself.
_INCONCLUSIVE = {401, 403, 429}


def is_public_url(url: str) -> bool:
    """True when ``url`` is http(s) and every address its host resolves to is public."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        infos = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def check_url(url: str, *, timeout: float = 5.0, transport=None) -> int | None:
    """The link's HTTP status, or None when it is unsafe or does not answer.

    shortcut: the host is resolved here and again by httpx, so DNS rebinding can
    slip a private address through; switch to the pinned safe fetcher from #64.
    """
    if not is_public_url(url):
        return None
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        ) as client:
            response = client.head(url)
            if response.status_code in (405, 501):  # HEAD not supported: ask for GET
                with client.stream("GET", url) as streamed:
                    return streamed.status_code
            return response.status_code
    except httpx.HTTPError:
        return None


def link_verdict(status: int | None) -> bool | None:
    """True alive, False dead, None inconclusive (try again on the next check)."""
    if status in _INCONCLUSIVE:
        return None
    return status is not None and status < 400
