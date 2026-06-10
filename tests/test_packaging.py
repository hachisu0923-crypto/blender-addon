"""Packaging + architecture guards (Phase 4.2).

Validates the Extension manifest and enforces the rule that ``core`` maths
modules stay bpy-free so they remain importable/testable without Blender.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "spectral_render"


def test_manifest_has_required_fields():
    with open(PKG / "blender_manifest.toml", "rb") as fh:
        m = tomllib.load(fh)
    for key in ("schema_version", "id", "version", "name", "type",
                "blender_version_min", "license"):
        assert key in m, f"manifest missing {key}"
    assert m["id"] == "spectral_render"
    assert m["type"] == "add-on"
    assert m["blender_version_min"] >= "4.2.0"


def test_core_modules_are_bpy_free():
    # node_group is the one intentionally bpy-bound core module; all the maths
    # modules must stay importable without Blender.
    for path in (PKG / "core").glob("*.py"):
        if path.name == "node_group.py":
            continue
        assert "import bpy" not in path.read_text(), f"{path.name} must not import bpy"


def test_node_group_is_the_only_core_bpy_module():
    # node_group is intentionally bpy-bound; it lives outside the pure-maths set.
    assert "import bpy" in (PKG / "core" / "node_group.py").read_text()


def test_bundled_data_exists():
    assert (PKG / "data" / "cie_1931_2deg.csv").exists()
    assert (PKG / "data" / "d65.csv").exists()
    assert list((PKG / "data" / "metals").glob("*.csv"))


def test_no_absolute_intra_package_imports():
    # Extensions load under a generated module name, so intra-addon imports must
    # be relative (never `import spectral_render...`).
    for path in PKG.rglob("*.py"):
        text = path.read_text()
        assert "import spectral_render" not in text, path
        assert "from spectral_render" not in text, path
