"""ADR 003: src/app is pure logic and never reaches up into the web layer."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "src" / "app"
FORBIDDEN = ("fastapi", "starlette", "assistant")
PARTS = (
    "ingest",
    "syllabus",
    "roadmap",
    "planner",
    "search",
    "vetting",
    "curator",
    "companion",
)


def forbidden_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return [module for module in modules if module.split(".")[0] in FORBIDDEN]


@pytest.mark.parametrize(
    "path", sorted(APP.rglob("*.py")), ids=lambda path: path.relative_to(APP).as_posix()
)
def test_app_does_not_import_the_web_layer(path):
    assert forbidden_imports(path) == [], "Keep HTTP code in assistant/backend (ADR 003)"


def test_checker_catches_lazy_and_dotted_imports(tmp_path):
    module = tmp_path / "leaky.py"
    module.write_text(
        "import json\n"
        "def handler():\n"
        "    from fastapi import HTTPException\n"
        "    import assistant.backend.models\n",
        encoding="utf-8",
    )
    assert forbidden_imports(module) == ["fastapi", "assistant.backend.models"]


@pytest.mark.parametrize("part", PARTS)
def test_every_spec_part_has_a_package(part):
    assert (APP / part / "__init__.py").is_file()


def test_old_backend_paths_still_re_export_the_moved_code():
    import app.companion
    import app.ingest
    import app.planner
    from assistant.backend import companion, ingest, scheduler

    assert ingest.extract_pages is app.ingest.extract_pages
    assert scheduler.build_plan is app.planner.build_plan
    assert companion.girlfriend_mode_allowed is app.companion.girlfriend_mode_allowed
