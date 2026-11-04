"""Is a resource link still alive? (spec 11.7)

Only public http(s) addresses are contacted, redirects are not followed and no
body is downloaded: the daily check needs a status code, not the page.
"""

import httpx

from app.vetting.fetch import FetchError, pinned_client, public_address, send_pinned

USER_AGENT = (
    "PathlyLinkCheck/1.0 "
    "(+https://github.com/Rokieroo/Group04-CS252-VirtualAssistant)"
)
# Sites that block bots or rate-limit say nothing about the link itself.
_INCONCLUSIVE = {401, 403, 429}


def is_public_url(url: str) -> bool:
    """True when ``url`` is http(s) and every address its host resolves to is public."""
    try:
        public_address(httpx.URL(url))
    except (FetchError, httpx.InvalidURL):
        return False
    return True


def check_url(url: str, *, timeout: float = 5.0, transport=None) -> int | None:
    """The link's HTTP status, or None when it is unsafe or does not answer."""
    try:
        target = httpx.URL(url)
        with pinned_client(transport) as client:
            for method in ("HEAD", "GET"):
                response = send_pinned(
                    client, method, target, timeout=timeout, user_agent=USER_AGENT
                )
                response.close()  # status only; a GET body is never read
                if response.status_code not in (405, 501):  # HEAD not supported: ask for GET
                    break
            return response.status_code
    except (FetchError, httpx.HTTPError, httpx.InvalidURL):
        return None


def link_verdict(status: int | None) -> bool | None:
    """True alive, False dead, None inconclusive (try again on the next check)."""
    if status in _INCONCLUSIVE:
        return None
    return status is not None and status < 400
