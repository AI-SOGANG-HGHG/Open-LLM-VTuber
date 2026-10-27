"""Check production build discovery without loading model dependencies."""

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from src.open_llm_vtuber.frontend_build import (
    frontend_distribution_dir,
    require_frontend_build,
)


class FrontendBuildTests(unittest.TestCase):
    """Exercise missing and available web build layouts."""

    def setUp(self) -> None:
        """Create an isolated fixture inside the ignored private directory."""
        self.fixture_parent = (
            Path(__file__).resolve().parents[1] / "private" / "test-fixtures"
        )
        self.root = self.fixture_parent / uuid4().hex
        self.root.mkdir(parents=True)
        self.addCleanup(self.remove_fixture)

    def remove_fixture(self) -> None:
        """Remove only this test's workspace fixture."""
        if self.root.resolve().parent != self.fixture_parent.resolve():
            raise ValueError("Test fixture is outside the expected directory")
        shutil.rmtree(self.root)

    def test_missing_build_explains_both_startup_modes(self) -> None:
        """Give actionable commands when a fresh clone has no build."""
        with self.assertRaises(FileNotFoundError) as result:
            require_frontend_build(self.root)
        message = str(result.exception)
        for command in (
            "npm ci --ignore-scripts",
            "npm run build:web",
            "--frontend-dev",
        ):
            self.assertIn(command, message)

    def test_source_html_is_not_a_production_build(self) -> None:
        """Reject the renderer template, which browsers cannot run directly."""
        source_dir = self.root / "frontend" / "src" / "renderer"
        source_dir.mkdir(parents=True)
        (source_dir / "index.html").write_text("<script src='src/main.tsx'></script>")
        with self.assertRaises(FileNotFoundError):
            require_frontend_build(self.root)

    def test_web_build_is_found(self) -> None:
        """Use the web output rather than the Electron renderer output."""
        build_dir = self.root / "frontend" / "dist" / "web"
        build_dir.mkdir(parents=True)
        (build_dir / "index.html").write_text("<div id='root'></div>")
        self.assertEqual(require_frontend_build(self.root), build_dir)

    def test_default_directory_is_relative_to_repository(self) -> None:
        """Resolve the repository using module location, not the shell location."""
        repo_root = Path(__file__).resolve().parents[1]
        with patch("os.getcwd", return_value=str(self.root)):
            self.assertEqual(
                frontend_distribution_dir(), repo_root / "frontend" / "dist" / "web"
            )


if __name__ == "__main__":
    unittest.main()
