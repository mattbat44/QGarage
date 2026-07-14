from __future__ import annotations

from qgarage.ui.scaffold_dialog import build_class_name, scaffold_app


class TestBuildClassName:
    def test_builds_pascal_case_app_name(self):
        assert build_class_name("my_cool_tool") == "MyCoolToolApp"


class TestScaffoldApp:
    def test_scaffolds_uv_app(self, tmp_path):
        dest_dir = scaffold_app(
            tmp_path,
            "demo_app",
            {
                "{{app_name}}": "Demo App",
                "{{app_id}}": "demo_app",
                "{{author}}": "Tester",
                "{{description}}": "Demo description",
                "{{class_name}}": "DemoApp",
            },
            "uv",
        )

        assert dest_dir == tmp_path / "demo_app"
        assert (dest_dir / "app_meta.json").exists()
        assert (dest_dir / "main.py").exists()
        assert (dest_dir / "requirements.txt").exists()
        assert not (dest_dir / "pixi.toml").exists()

    def test_scaffolds_pixi_app(self, tmp_path):
        dest_dir = scaffold_app(
            tmp_path,
            "pixi_app",
            {
                "{{app_name}}": "Pixi App",
                "{{app_id}}": "pixi_app",
                "{{author}}": "Tester",
                "{{description}}": "Pixi description",
                "{{class_name}}": "PixiApp",
            },
            "pixi",
        )

        assert dest_dir == tmp_path / "pixi_app"
        assert (dest_dir / "app_meta.json").exists()
        assert (dest_dir / "main.py").exists()
        assert (dest_dir / "pixi.toml").exists()
        assert not (dest_dir / "requirements.txt").exists()

    def test_rejects_unknown_backend(self, tmp_path):
        replacements = {
            "{{app_name}}": "Broken App",
            "{{app_id}}": "broken_app",
            "{{author}}": "Tester",
            "{{description}}": "Broken description",
            "{{class_name}}": "BrokenApp",
        }

        try:
            scaffold_app(tmp_path, "broken_app", replacements, "unknown")
        except ValueError as exc:
            assert "Unsupported backend" in str(exc)
        else:
            raise AssertionError("Expected ValueError for unsupported backend")
