"""Locate the web build produced from the team's frontend source."""

from pathlib import Path


def frontend_distribution_dir(project_root: Path | None = None) -> Path:
    """Return the production web output directory.

    Args:
        project_root: Repository root; defaults to this module's repository.

    Returns:
        Path to the Vite web build, independent of the working directory.
    """
    root = (
        project_root
        if project_root is not None
        else Path(__file__).resolve().parents[2]
    )
    return root / "frontend" / "dist" / "web"


def require_frontend_build(project_root: Path | None = None) -> Path:
    """Find a built web entry point or explain how to create one.

    Args:
        project_root: Repository root; defaults to this module's repository.

    Returns:
        Directory containing the production web entry point.

    Raises:
        FileNotFoundError: If the frontend has not been built.
    """
    directory = frontend_distribution_dir(project_root)
    if not (directory / "index.html").is_file():
        raise FileNotFoundError(
            f"Frontend web build missing: {directory / 'index.html'}. "
            "In frontend/, run 'npm ci --ignore-scripts' and 'npm run build:web'. "
            "For development, start the backend with '--frontend-dev' and "
            "run 'npm run dev:web' in frontend/. See docs/frontend-development.md."
        )
    return directory
