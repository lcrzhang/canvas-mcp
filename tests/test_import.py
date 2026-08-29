"""Smoke test for the scaffold: the package must be installed, not merely
importable from the working directory."""

from pathlib import Path

import canvas_mcp


def test_package_imports_with_a_version() -> None:
    assert canvas_mcp.__version__


def test_package_is_imported_from_the_src_layout() -> None:
    # A src layout means an accidental `import canvas_mcp` from the repo root
    # cannot work; this fails loudly if the editable install is missing.
    assert Path(canvas_mcp.__file__).parent.name == "canvas_mcp"
