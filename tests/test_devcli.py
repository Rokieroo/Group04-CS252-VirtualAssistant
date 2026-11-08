import json

from devcli.__main__ import build_parser
from devcli.ai import BENCHMARK, RESOURCES, load_cases, load_resources
from devcli.conventions import check_branch, check_commit
from devcli.db import init_db, scan_text
from devcli.qa import REPORT_TEMPLATE


def test_parser_has_all_domains():
    parser = build_parser()
    for argv in (["ui", "dev"], ["ai", "benchmark", "validate"], ["db", "init"], ["qa", "lint"], ["devops", "ci"]):
        assert parser.parse_args(argv).func


def test_branch_names():
    assert check_branch("ai-minh/12-item-generation") is None
    assert check_branch("uiux-thinh/3-upload-page") is None
    assert check_branch("main") is None
    assert check_branch("claude/project-thread-zsdgmy") is None
    assert check_branch("minh-ai/feature") is not None
    assert check_branch("feature/login") is not None
    assert check_branch("ai-minh/item-generation") is not None


def test_commit_messages():
    assert check_commit("feat(ai): add item generation prompt") is None
    assert check_commit("fix(db): 🐛 drop duplicate index") is None
    assert check_commit("docs: update readme\n\nlonger body") is None
    assert check_commit("Merge pull request #3 from MorganConsort/UI/UX") is None
    assert check_commit("update code") is not None
    assert check_commit("feature(ai): add prompt") is not None
    assert check_commit("feat(ai): " + "x" * 120) is not None


def test_benchmark_file_is_valid():
    cases, errors = load_cases(BENCHMARK)
    assert errors == []
    assert len(cases) >= 5


def test_benchmark_catches_errors(tmp_path):
    bad = tmp_path / "bad.jsonl"
    rows = [
        {"id": "X1", "use_case": "UC-1", "kind": "normal", "question": "q", "expected": "e"},
        {"id": "X1", "use_case": "UC-02", "kind": "weird", "question": "q", "expected": "e"},
    ]
    bad.write_text("\n".join(json.dumps(r) for r in rows) + "\n{not json", encoding="utf-8")
    _, errors = load_cases(bad)
    assert len(errors) == 4


def test_resources_file_is_valid():
    nodes, errors = load_resources(RESOURCES)
    assert errors == []
    assert len(nodes) >= 30


def test_resources_catches_errors(tmp_path):
    bad = tmp_path / "resources.jsonl"
    good = {"url": "https://a.example", "label": "good", "reason": "r"}
    rows = [
        {"id": "R01", "node": {"title": "t"}, "resources": [good, {**good, "label": "ok"}]},
        {"id": "R01", "node": {}, "resources": []},
    ]
    bad.write_text("\n".join(json.dumps(r) for r in rows) + "\n{not json", encoding="utf-8")
    _, errors = load_resources(bad)
    assert len(errors) == 5


def test_init_db_creates_tables(tmp_path):
    tables = init_db(tmp_path / "t.db")
    for name in ("users", "sources", "items", "reviews", "companion_events"):
        assert name in tables


def test_scan_text_finds_fake_key():
    fake = "sk-" + "a" * 32
    assert scan_text(f"OPENAI_API_KEY={fake}") == ["OpenAI key"]
    assert scan_text("no secrets here") == []
    assert scan_text("https://www.nist.gov/itl/ai-risk-management-framework") == []


def test_report_template_formats():
    text = REPORT_TEMPLATE.format(week=1, today="2026-10-24")
    assert text.startswith("# Báo cáo QA tuần 1")


def test_catalog_ingest_fills_csc10014_from_the_hand_lists_twice_without_new_rows(
    tmp_path, monkeypatch, capsys
):
    # Offline: only the hand-list connectors run, into a throwaway database.
    from devcli.ai import SYLLABUS_DIR

    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "catalog.db").as_posix())
    gold = str(SYLLABUS_DIR / "01_csc10014_problem_framing.gold.json")
    argv = ["ai", "catalog-ingest", "--syllabus", gold,
            "--connector", "manual_yaml", "--connector", "open_yale"]

    args = build_parser().parse_args(argv)
    assert args.func(args) == 0
    first = capsys.readouterr().out
    assert args.func(args) == 0
    second = capsys.readouterr().out

    assert "== CSC10014: 7/7 chặng có >= 5 ứng viên pending/verified" in first
    assert "[ OK ] manual_yaml" in first and "tạo {'courses'" in first
    assert "tạo {}" in second and "7/7" in second
