"""Architecture guard: technology imports stay inside their adapter packages, and core stays pure.

- playwright                      only under hands/surfaces/browser/
- pyobjc (AppKit, Quartz, ...)    only under hands/surfaces/desktop_macos/
- hands.core                      imports nothing from other hands packages
Imports are read with `ast`, so imports inside functions and try-blocks are caught too.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

HANDS_ROOT = Path(__file__).resolve().parents[1] / "src" / "hands"
PYOBJC_MODULES = ("ApplicationServices", "Quartz", "AppKit", "objc", "Foundation", "Cocoa", "CoreFoundation",
                  "PyObjCTools")


@dataclass(frozen=True)
class ImportedModule:
    importer: str  # dotted module name of the importing file, e.g. 'hands.core.ports'
    module: str  # absolute dotted name that was imported


def module_name_for(path: Path, package_root: Path) -> str:
    relative = path.relative_to(package_root.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imported_modules(source: str, importer: str, is_package: bool = False) -> list[ImportedModule]:
    """Every module a source file imports, with relative imports resolved against `importer`."""
    found: list[ImportedModule] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(ImportedModule(importer, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from_import(node, importer, is_package)
            found.extend(ImportedModule(importer, _join(base, alias.name)) for alias in node.names)
    return found


def _resolve_from_import(node: ast.ImportFrom, importer: str, is_package: bool) -> str:
    if node.level == 0:
        return node.module or ""
    package_parts = importer.split(".") if is_package else importer.split(".")[:-1]
    base_parts = package_parts[: len(package_parts) - (node.level - 1)]
    return ".".join([*base_parts, *([node.module] if node.module else [])])


def _join(base: str, name: str) -> str:
    """'from a.b import c' may import submodule a.b.c; recording it that way closes 'from .. import x'."""
    if name == "*" or not base:
        return base or name
    return f"{base}.{name}"


def top_level(module: str) -> str:
    return module.split(".")[0]


def boundary_violations(imports: list[ImportedModule]) -> list[str]:
    violations: list[str] = []
    for imported in imports:
        root = top_level(imported.module)
        if root == "playwright" and not imported.importer.startswith("hands.surfaces.browser"):
            violations.append(f"{imported.importer} imports playwright ({imported.module})")
        if root in PYOBJC_MODULES and not imported.importer.startswith("hands.surfaces.desktop_macos"):
            violations.append(f"{imported.importer} imports pyobjc module {imported.module}")
        core_reaches_out = (
            imported.importer.startswith("hands.core")
            and root == "hands"
            and not imported.module.startswith("hands.core")
        )
        if core_reaches_out:
            violations.append(f"{imported.importer} (core) imports {imported.module}")
    return violations


def all_hands_imports() -> list[ImportedModule]:
    imports: list[ImportedModule] = []
    for path in sorted(HANDS_ROOT.rglob("*.py")):
        importer = module_name_for(path, HANDS_ROOT)
        imports.extend(imported_modules(path.read_text(encoding="utf-8"), importer, path.name == "__init__.py"))
    return imports


# ---------------------------------------------------------------- the real check


def test_source_tree_exists() -> None:
    assert (HANDS_ROOT / "core" / "ports.py").is_file()


def test_no_import_boundary_violations() -> None:
    assert boundary_violations(all_hands_imports()) == []


# ---------------------------------------------------------------- the checker itself


@pytest.mark.parametrize(
    ("importer", "source", "expected_count"),
    [
        ("hands.replay.engine", "import playwright", 1),
        ("hands.replay.engine", "from playwright.async_api import Page", 1),
        ("hands.replay.engine", "def f():\n    import playwright.async_api as pw\n", 1),
        ("hands.surfaces.browser.surface", "from playwright.async_api import Page", 0),
        ("hands.surfaces.fake", "import Quartz", 1),
        ("hands.session.console", "from AppKit import NSWorkspace", 1),
        ("hands.surfaces.desktop_macos.surface", "import ApplicationServices\nimport objc", 0),
        ("hands.core.ports", "from hands.surfaces import fake", 1),
        ("hands.core.ports", "from hands.core.actions import Action", 0),
        ("hands.core.ports", "from ..replay import engine", 1),
        ("hands.core.ports", "from . import actions", 0),
        ("hands.core.ports", "from .. import replay", 1),
        ("hands.core.ports", "from hands import surfaces", 1),
        ("hands.locate.resolve", "from hands.surfaces.fake import FakeSurface", 0),
        ("hands.core.ports", "", 0),
    ],
)
def test_boundary_checker_flags_expected_imports(importer: str, source: str, expected_count: int) -> None:
    assert len(boundary_violations(imported_modules(source, importer))) == expected_count


def test_relative_imports_resolve_against_the_importer() -> None:
    imports = imported_modules("from .actions import Action\nfrom .. import surfaces", "hands.core.ports")
    assert [imported.module for imported in imports] == ["hands.core.actions.Action", "hands.surfaces"]


def test_relative_imports_in_package_init_resolve_against_the_package() -> None:
    imports = imported_modules("from .surface import BrowserSurface", "hands.surfaces.browser", is_package=True)
    assert [imported.module for imported in imports] == ["hands.surfaces.browser.surface.BrowserSurface"]


def test_module_name_for_package_init() -> None:
    init_path = HANDS_ROOT / "surfaces" / "__init__.py"
    assert module_name_for(init_path, HANDS_ROOT) == "hands.surfaces"
