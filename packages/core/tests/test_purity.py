"""NFR-4: tandem_core imports no file, network, process, clock, or randomness modules."""

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "tandem_core"

FORBIDDEN_MODULES = {
    "os",
    "io",
    "pathlib",
    "shutil",
    "tempfile",
    "glob",
    "socket",
    "ssl",
    "select",
    "urllib",
    "http",
    "requests",
    "httpx",
    "httpx2",
    "aiohttp",
    "sqlite3",
    "subprocess",
    "multiprocessing",
    "threading",
    "asyncio",
    "time",
    "random",
    "secrets",
    "uuid",
    "yaml",
    "openpyxl",
    "pdfplumber",
    "litellm",
}
FORBIDDEN_CALLS = {"open", "input", "print", "exec", "eval"}
FORBIDDEN_ATTRS = {
    ("date", "today"),
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("datetime", "today"),
}

FILES = sorted(CORE.rglob("*.py"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(CORE)))
def test_core_module_is_pure(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            names = []
        problems += [f"imports {n}" for n in names if n.split(".")[0] in FORBIDDEN_MODULES]
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FORBIDDEN_CALLS
        ):
            problems.append(f"calls {node.func.id}()")
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and (node.value.id, node.attr) in FORBIDDEN_ATTRS
        ):
            problems.append(f"uses {node.value.id}.{node.attr}")
    assert not problems, f"{path.name}: {problems}"
