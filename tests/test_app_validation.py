"""Validate that new apps conform to the QGarage framework contract.

These tests check the *structure* of an app (meta schema, file presence,
class hierarchy) without requiring QGIS or uv at runtime. Use them as a
gate when installing or developing new apps.
"""

import json
import textwrap
from pathlib import Path

import pytest

from qgarage.core.constants import (
    APP_META_FILENAME,
    DEFAULT_ENTRY_POINT,
    DEFAULT_CLASS_NAME,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_META_FIELDS = {"id"}
EXPECTED_META_FIELDS = {
    "id",
    "name",
    "version",
    "description",
    "entry_point",
    "class_name",
    "tags",
}


def validate_app_meta(meta: dict) -> list[str]:
    """Return a list of validation errors for an app_meta dict."""
    errors = []
    if not isinstance(meta, dict):
        return ["app_meta.json must be a JSON object"]

    for field in REQUIRED_META_FIELDS:
        if field not in meta or not meta[field]:
            errors.append(f"Missing required field: '{field}'")

    app_id = meta.get("id", "")
    if app_id and not app_id.replace("_", "").isalnum():
        errors.append(f"'id' must be alphanumeric/underscores, got: '{app_id}'")

    if "tags" in meta and not isinstance(meta["tags"], list):
        errors.append("'tags' must be a list")

    return errors


def validate_app_structure(app_dir: Path) -> list[str]:
    """Return a list of structural errors for an app directory."""
    errors = []

    meta_file = app_dir / APP_META_FILENAME
    if not meta_file.exists():
        errors.append(f"{APP_META_FILENAME} not found")
        return errors

    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON in {APP_META_FILENAME}: {e}")
        return errors

    errors.extend(validate_app_meta(meta))

    entry = meta.get("entry_point", DEFAULT_ENTRY_POINT)
    if not (app_dir / entry).exists():
        errors.append(f"Entry point '{entry}' not found")

    return errors


def validate_app_class(app_dir: Path) -> list[str]:
    """Validate that the entry point contains a valid BaseApp subclass.

    This imports the module, so it requires qgarage.core.base_app to be
    importable (but NOT QGIS at the module level — we mock the heavy bits).
    """
    import importlib.util

    errors = []
    meta_file = app_dir / APP_META_FILENAME
    meta = json.loads(meta_file.read_text(encoding="utf-8"))

    entry = app_dir / meta.get("entry_point", DEFAULT_ENTRY_POINT)
    class_name = meta.get("class_name", DEFAULT_CLASS_NAME)

    spec = importlib.util.spec_from_file_location(f"_test_app.{meta['id']}", str(entry))
    if spec is None or spec.loader is None:
        errors.append(f"Cannot create module spec for {entry}")
        return errors

    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        errors.append(f"Failed to import {entry}: {e}")
        return errors

    klass = getattr(module, class_name, None)
    if klass is None:
        errors.append(f"Class '{class_name}' not found in {entry.name}")
        return errors

    from qgarage.core.base_app import BaseApp

    if not issubclass(klass, BaseApp):
        errors.append(f"'{class_name}' does not inherit from BaseApp")
        return errors

    # Verify it can be instantiated
    try:
        instance = klass(app_meta=meta, app_dir=app_dir)
    except Exception as e:
        errors.append(f"Failed to instantiate '{class_name}': {e}")
        return errors

    # Must have execute_logic
    if not callable(getattr(instance, "execute_logic", None)):
        errors.append(f"'{class_name}' missing execute_logic method")

    return errors


# ---------------------------------------------------------------------------
# Tests — app_meta.json schema
# ---------------------------------------------------------------------------


class TestAppMetaValidation:
    def test_valid_meta_passes(self):
        meta = {"id": "my_app", "name": "My App", "version": "1.0", "tags": ["demo"]}
        assert validate_app_meta(meta) == []

    def test_missing_id_fails(self):
        errors = validate_app_meta({"name": "No ID"})
        assert any("id" in e for e in errors)

    def test_empty_id_fails(self):
        errors = validate_app_meta({"id": ""})
        assert any("id" in e for e in errors)

    def test_invalid_id_characters(self):
        errors = validate_app_meta({"id": "my-app!"})
        assert any("alphanumeric" in e for e in errors)

    def test_underscore_id_ok(self):
        errors = validate_app_meta({"id": "my_cool_app"})
        assert errors == []

    def test_tags_must_be_list(self):
        errors = validate_app_meta({"id": "x", "tags": "not-a-list"})
        assert any("tags" in e for e in errors)

    def test_non_dict_meta(self):
        errors = validate_app_meta("not a dict")
        assert any("JSON object" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests — app directory structure
# ---------------------------------------------------------------------------


class TestAppStructureValidation:
    def test_valid_structure(self, make_app_dir):
        d = make_app_dir({"id": "good", "name": "Good"}, main_py="pass")
        assert validate_app_structure(d) == []

    def test_missing_meta_file(self, tmp_path):
        d = tmp_path / "no_meta"
        d.mkdir()
        errors = validate_app_structure(d)
        assert any("not found" in e for e in errors)

    def test_invalid_json_in_meta(self, tmp_path):
        d = tmp_path / "bad_json"
        d.mkdir()
        (d / "app_meta.json").write_text("{bad", encoding="utf-8")
        errors = validate_app_structure(d)
        assert any("Invalid JSON" in e for e in errors)

    def test_missing_entry_point(self, make_app_dir):
        d = make_app_dir({"id": "no_main", "name": "No Main"})  # no main_py
        errors = validate_app_structure(d)
        assert any("Entry point" in e for e in errors)

    def test_custom_entry_point(self, make_app_dir):
        d = make_app_dir(
            {"id": "custom", "name": "Custom", "entry_point": "run.py"},
            main_py=None,
        )
        # Missing custom entry point
        errors = validate_app_structure(d)
        assert any("run.py" in e for e in errors)

        # Now create it
        (d / "run.py").write_text("pass", encoding="utf-8")
        assert validate_app_structure(d) == []


# ---------------------------------------------------------------------------
# Tests — class contract validation
# ---------------------------------------------------------------------------


class TestAppClassValidation:
    def test_valid_app_class(self, make_app_dir):
        from tests.conftest import MINIMAL_MAIN_PY, MINIMAL_META

        d = make_app_dir(MINIMAL_META, main_py=MINIMAL_MAIN_PY)
        assert validate_app_class(d) == []

    def test_missing_class(self, make_app_dir):
        meta = {**dict(id="bad_class", name="Bad", class_name="DoesNotExist")}
        d = make_app_dir(meta, main_py="x = 1\n")
        errors = validate_app_class(d)
        assert any("not found" in e for e in errors)

    def test_class_not_subclass_of_baseapp(self, make_app_dir):
        meta = {"id": "not_base", "name": "Not Base", "class_name": "FakeApp"}
        code = textwrap.dedent("""\
            class FakeApp:
                def execute_logic(self, inputs):
                    return {"status": "success"}
        """)
        d = make_app_dir(meta, main_py=code)
        errors = validate_app_class(d)
        assert any("BaseApp" in e for e in errors)

    def test_syntax_error_in_main(self, make_app_dir):
        meta = {"id": "syntax_err", "name": "Syntax"}
        d = make_app_dir(meta, main_py="def broken(:\n")
        errors = validate_app_class(d)
        assert any("Failed to import" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests — validate the bundled hello_world app
# ---------------------------------------------------------------------------


class TestHelloWorldApp:
    """Ensure the shipped example app passes all validation gates."""

    @pytest.fixture
    def hello_dir(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent / "qgarage" / "apps" / "hello_world"
        )

    def test_structure(self, hello_dir):
        if not hello_dir.exists():
            pytest.skip("hello_world app not present")
        assert validate_app_structure(hello_dir) == []

    def test_meta_schema(self, hello_dir):
        if not hello_dir.exists():
            pytest.skip("hello_world app not present")
        meta = json.loads((hello_dir / "app_meta.json").read_text(encoding="utf-8"))
        assert validate_app_meta(meta) == []

    def test_class_contract(self, hello_dir):
        if not hello_dir.exists():
            pytest.skip("hello_world app not present")
        assert validate_app_class(hello_dir) == []
