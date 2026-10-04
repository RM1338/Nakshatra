"""algo/ and graph/ must stay pure: no network, database or web framework (ARCH §4)."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "nakshatra"
BANNED = {"httpx", "requests", "sqlite3", "fastapi", "starlette", "uvicorn", "socket", "urllib", "nakshatra.store",
          "nakshatra.serp", "nakshatra.api", "nakshatra.orchestrator"}


@pytest.mark.parametrize("path", sorted((ROOT / "algo").glob("*.py")) + sorted((ROOT / "graph").glob("*.py")),
                         ids=lambda p: p.name)
def test_no_io_imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
            [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        for n in names:
            assert not any(n == b or n.startswith(b + ".") for b in BANNED), f"{path.name} imports {n}"
