"""Issue #64: safe fetcher (SSRF), domain policy, paywall rules, and strip_pii."""

import httpx
import pytest

from app.search import strip_pii
from app.vetting import DomainPolicy, DomainTier, SafeFetcher, domain_tier

PUBLIC = "93.184.216.34"
DNS = {
    "example.org": [PUBLIC],
    "www.scribd.com": ["151.101.2.152"],
    "rebind.example": [PUBLIC, "10.0.0.7"],
    "metadata.example": ["169.254.169.254"],
}


def resolver(host, port):
    return DNS.get(host, [host])  # literal addresses resolve to themselves


def fetcher(routes, contacted=None, **options):
    """Serve ``routes`` keyed by "host/path"; robots.txt is 404 unless routed."""

    def reply(request):
        key = request.headers["host"] + request.url.path
        if contacted is not None:
            contacted.append((str(request.url), key, request.headers.get("cookie")))
        if key in routes:
            route = routes[key]
            return route(request) if callable(route) else route
        return httpx.Response(404)

    return SafeFetcher(resolver=resolver, transport=httpx.MockTransport(reply), **options)


def page(html="<p>Recursion explained step by step.</p>", status=200, **headers):
    return httpx.Response(status, html=html, headers=headers)


def redirect(location):
    return httpx.Response(302, headers={"Location": location})


# --- SSRF -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.example/latest/meta-data/",
        "http://127.0.0.1:8000/admin",
        "http://10.0.0.5/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
        "http://rebind.example/",  # one private answer is enough to refuse
    ],
)
def test_internal_addresses_are_never_contacted(url):
    contacted = []
    result = fetcher({}, contacted).fetch(url)
    assert result.error == "private_address"
    assert not result.ok
    assert contacted == []


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://example.org/", "gopher://example.org/", "notaurl"]
)
def test_only_http_and_https(url):
    contacted = []
    assert fetcher({}, contacted).fetch(url).error in {"bad_scheme", "invalid_url"}
    assert contacted == []


def test_redirect_to_loopback_is_refused_before_it_is_followed():
    contacted = []
    result = fetcher({"example.org/go": redirect("http://127.0.0.1/admin")}, contacted).fetch(
        "https://example.org/go"
    )
    assert result.error == "private_address"
    assert all("127.0.0.1" not in url for url, _key, _cookie in contacted)


def test_connects_to_the_checked_address_with_the_hostname_in_host():
    contacted = []
    result = fetcher({"example.org/notes": page()}, contacted).fetch("https://example.org/notes")
    assert result.ok
    url, key, _cookie = contacted[-1]
    assert url == f"https://{PUBLIC}/notes"  # pinned: no second DNS lookup to rebind
    assert key == "example.org/notes"


def test_at_most_three_redirects():
    chain = {f"example.org/{i}": redirect(f"/{i + 1}") for i in range(4)}
    assert fetcher({**chain, "example.org/3": page()}).fetch("https://example.org/0").ok
    assert fetcher({**chain, "example.org/4": page()}).fetch(
        "https://example.org/0"
    ).error == "too_many_redirects"


def test_cookies_are_never_sent():
    contacted = []
    routes = {
        "example.org/a": httpx.Response(
            302, headers={"Location": "/b", "Set-Cookie": "session=secret; Path=/"}
        ),
        "example.org/b": page(),
    }
    assert fetcher(routes, contacted).fetch("https://example.org/a").ok
    assert [cookie for _url, _key, cookie in contacted] == [None] * len(contacted)


# --- size and time ----------------------------------------------------------------------


def test_six_megabyte_file_is_refused():
    six_mb = b"x" * (6 * 1024 * 1024)
    declared = fetcher({"example.org/big.pdf": httpx.Response(200, content=six_mb)})
    assert declared.fetch("https://example.org/big.pdf").error == "too_large"

    def undeclared(request):  # chunked: no Content-Length to trust
        return httpx.Response(200, content=iter([six_mb[:4_000_000], six_mb[4_000_000:]]))

    streamed = fetcher({"example.org/big.pdf": undeclared})
    assert streamed.fetch("https://example.org/big.pdf").error == "too_large"


def test_timeout_is_reported():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    assert fetcher({"example.org/slow": slow}).fetch("https://example.org/slow").error == "timeout"


# --- robots.txt -------------------------------------------------------------------------


def test_robots_disallow_is_respected_and_cached():
    contacted = []
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
    f = fetcher(
        {"example.org/robots.txt": robots, "example.org/open": page(),
         "example.org/private/x": page()},
        contacted,
    )
    assert f.fetch("https://example.org/private/x").error == "robots"
    assert f.fetch("https://example.org/open").ok
    assert [key for _url, key, _cookie in contacted].count("example.org/robots.txt") == 1


def test_unreachable_robots_allows_nothing():
    routes = {"example.org/robots.txt": httpx.Response(503), "example.org/open": page()}
    assert fetcher(routes).fetch("https://example.org/open").error == "robots"


def test_rules_for_other_bots_do_not_apply():
    # Wikipedia's robots.txt shuts out "Fetch"; robotparser matches by substring.
    robots = httpx.Response(200, text="User-agent: Fetch\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    routes = {"example.org/robots.txt": robots, "example.org/open": page()}
    assert fetcher(routes).fetch("https://example.org/open").ok


# --- paywall and login rules --------------------------------------------------------------


@pytest.mark.parametrize(
    ("routes", "url", "reason"),
    [
        ({"example.org/x": page(status=401)}, "https://example.org/x", "http_401"),
        ({"example.org/x": page(status=403)}, "https://example.org/x", "http_403"),
        (
            {"example.org/x": page('<form><input name="p" type="password"></form>')},
            "https://example.org/x",
            "login_form",
        ),
        (
            {"example.org/x": redirect("/login?next=/x"), "example.org/login": page()},
            "https://example.org/x",
            "login_redirect",
        ),
        ({"www.scribd.com/doc/1": page()}, "https://www.scribd.com/doc/1", "known_domain"),
    ],
)
def test_login_and_paywall_pages_are_flagged(routes, url, reason):
    result = fetcher(routes).fetch(url)
    assert result.paywall == reason
    assert not result.ok


def test_good_page_passes_with_a_stable_hash():
    f = fetcher({"example.org/notes": page()})
    first, second = f.fetch("https://example.org/notes"), f.fetch("https://example.org/notes")
    assert first.ok and first.paywall is None
    assert first.content_hash == second.content_hash
    assert "Recursion" in first.text


# --- domain policy ----------------------------------------------------------------------

PIRATED = [
    "https://libgen.rs/book/index.php?md5=abc",
    "http://libgen.is/search.php?req=algorithms",
    "https://www.libgen.li/ads.php",
    "https://library.lol/main/ABC",
    "https://z-lib.org/",
    "https://z-library.sk/book/123",
    "https://singlelogin.re/",
    "https://1lib.sk/book/1",
    "https://b-ok.cc/book/42",
    "https://sci-hub.se/10.1145/3290605",
    "https://SCI-HUB.RU/10.1000/xyz",
    "https://annas-archive.org/md5/abc",
    "https://annas-archive.li/search?q=clrs",
    "https://www.pdfdrive.com/introduction-to-algorithms-e1.html",
    "https://dokumen.pub/clrs.html",
    "https://ebin.pub/clrs.html",
    "https://pdfcoffee.com/clrs-pdf-free.html",
    "https://www.chegg.com/homework-help/questions-and-answers/q1",
    "https://www.coursehero.com/file/123/Final-Exam-Answers/",
    "https://thepiratebay.org/search.php?q=textbook",
]


def test_twenty_pirated_urls_are_all_blocked():
    assert len(set(PIRATED)) == 20
    leaked = [url for url in PIRATED if domain_tier(url) is not DomainTier.BLOCKED]
    assert leaked == []


def test_blocked_domain_is_refused_even_after_a_redirect():
    contacted = []
    routes = {"example.org/book": redirect("https://libgen.rs/book/1")}
    result = fetcher(routes, contacted).fetch("https://example.org/book")
    assert result.error == "blocked_domain"
    assert all("libgen" not in key for _url, key, _cookie in contacted)


@pytest.mark.parametrize(
    ("url", "tier"),
    [
        ("https://www.fit.hcmus.edu.vn/syllabus", DomainTier.TIER1),
        ("https://ocw.mit.edu/courses/6-006", DomainTier.TIER1),
        ("https://docs.python.org/3/tutorial/", DomainTier.TIER1),
        ("https://vi.wikipedia.org/wiki/Đệ_quy", DomainTier.TIER2),
        ("https://some-blog.example/post", DomainTier.OTHER),
        ("https://notlibgen.com/", DomainTier.OTHER),  # a suffix match needs a whole label
        ("not a url", DomainTier.BLOCKED),
    ],
)
def test_domain_tiers(url, tier):
    assert domain_tier(url) is tier


def test_policy_files_are_plain_lists(tmp_path):
    (tmp_path / "blocklist.txt").write_text("# comment\nbad.example\nmirror.*\n")
    (tmp_path / "allowlist_tier1.txt").write_text("good.example  # trusted\n")
    policy = DomainPolicy.load(tmp_path)
    assert policy.tier("https://cdn.bad.example/x") is DomainTier.BLOCKED
    assert policy.tier("https://mirror.anything.io/") is DomainTier.BLOCKED
    assert policy.tier("https://good.example/") is DomainTier.TIER1
    assert policy.tier("https://other.example/") is DomainTier.OTHER


# --- strip_pii on syllabus headers --------------------------------------------------------

SYLLABI = [
    (
        ("ĐỀ CƯƠNG MÔN HỌC CS252 – Tư duy tính toán\nGiảng viên: ThS. Nguyễn Văn An\n"
        "Email: nvan@fit.hcmus.edu.vn – ĐT: 0909 123 456"),
        ["Nguyễn Văn An", "nvan@fit.hcmus.edu.vn", "0909 123 456"],
    ),
    (
        ("Giảng viên phụ trách: TS. Trần Thị Bích Ngọc (ttbngoc@hcmus.edu.vn)\n"
        "Điện thoại văn phòng: (028) 3835 4266"),
        ["Trần Thị Bích Ngọc", "ttbngoc@hcmus.edu.vn", "3835 4266"],
    ),
    (
        ("Course: Data Structures (CSC10004)\nInstructor: Dr. Le Hoang Dung\n"
        "E-mail: lhdung@gmail.com\nPhone: +84 912 345 678"),
        ["Le Hoang Dung", "lhdung@gmail.com", "912 345 678"],
    ),
    ("Lecturer: Pham Minh Chau, PhD — office I.101, Mon 9:00-11:00", ["Pham Minh Chau"]),
    (
        "Nhóm 04 thực hiện:\n- 22120123 – Võ Thanh Tâm\n- 22120456 – Đặng Quốc Bảo",
        ["22120123", "Võ Thanh Tâm", "22120456", "Đặng Quốc Bảo"],
    ),
    (
        "Giảng viên: Cô Mai Anh Thư\nTrợ giảng: Kha Tuấn Minh (MSSV 21127001)",
        ["Mai Anh Thư", "Kha Tuấn Minh", "21127001"],
    ),
    (
        "Giảng viên: Huỳnh Thị Kim Liên, Bùi Tiến Lên\nGiờ tiếp sinh viên: thứ Ba, phòng E.302",
        ["Huỳnh Thị Kim Liên", "Bùi Tiến Lên"],
    ),
    (
        "GV: Lê Ngọc Thành | lnthanh@fit.hcmus.edu.vn | 0283.835.4266",
        ["Lê Ngọc Thành", "lnthanh@fit.hcmus.edu.vn", "0283.835.4266"],
    ),
    (
        "Giảng viên: Châu Thành Đức\nTeaching assistant: Ông Văn Khoa\nZalo: 0987-654-321",
        ["Châu Thành Đức", "Ông Văn Khoa", "0987-654-321"],
    ),
    (
        "Giảng viên: Dr. John Smith (john.smith@uni.edu)\nStudent ID: SE170123",
        ["John Smith", "john.smith@uni.edu", "SE170123"],
    ),
]


@pytest.mark.parametrize(("syllabus", "secrets"), SYLLABI)
def test_strip_pii_removes_everything_from_sample_syllabi(syllabus, secrets):
    stripped = strip_pii(syllabus)
    assert [secret for secret in secrets if secret in stripped] == []
    assert stripped.count("\n") == syllabus.count("\n")  # lines survive for later parsing
    assert strip_pii(stripped) == stripped  # idempotent


def test_strip_pii_keeps_course_content():
    text = "Giảng viên: ThS. Nguyễn Văn An\nChương 2: Problem framing và CS252, năm 2025"
    assert strip_pii(text).splitlines()[1] == "Chương 2: Problem framing và CS252, năm 2025"


# --- per-domain rate limit (#98) ------------------------------------------------------


def test_throttle_spaces_requests_per_domain_at_its_rate():
    from app.vetting.fetch import DomainThrottle

    now, slept = [0.0], []

    def sleep(seconds):
        slept.append(round(seconds, 3))
        now[0] += seconds

    throttle = DomainThrottle({"ocw.mit.edu": 1, "zenodo.org": 0.1}, default=2,
                              clock=lambda: now[0], sleep=sleep)
    for host in ["ocw.mit.edu", "ocw.mit.edu", "zenodo.org", "zenodo.org", "example.org", "example.org"]:
        throttle.wait(host)
    # 1 s for MIT, 10 s for Zenodo, 0.5 s for an unlisted host; hosts never wait on each other.
    assert slept == [1.0, 10.0, 0.5]
    assert throttle.interval("www.ocw.mit.edu") == 1.0


def test_fetcher_throttles_robots_and_pages_alike():
    from app.vetting.fetch import DomainThrottle

    waited = []

    class Recorder(DomainThrottle):
        def wait(self, host):
            waited.append(host)

    with fetcher({"example.org/notes": page()}, throttle=Recorder()) as client:
        assert client.fetch("https://example.org/notes").ok
        assert client.fetch("https://example.org/notes").ok
    # robots.txt once (then cached), the page twice: every request is spaced.
    assert waited == ["example.org"] * 3
