"""Application paths and resource management.

This module provides functions for accessing:
- Per-user application data directory (for logs and settings)
- Bundled assets (QSS themes, icons) via importlib.resources
- Works both from source and when installed from wheels

The module uses platformdirs to determine platform-appropriate paths
for application data, and importlib.resources for accessing packaged assets.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path

from platformdirs import user_data_dir

# Application metadata constants
APP_NAME = "get-gphotos-data"
APP_ORG = "ExampleOrg"
_ASSETS_DIR = "assets"  # Directory name within package for assets
_DEFAULT_VERSION = "0.2.0"  # Fallback version if unable to determine


def app_version() -> str:
    """Get the application version.

    Tries multiple approaches:
    1. importlib.metadata.version() (works when installed)
    2. Reading pyproject.toml from source tree (development mode)
    3. Returns default version as fallback

    Returns:
        Version string (e.g., "0.2.0")
    """
    # Try package metadata first (works when installed)
    try:
        return version(APP_NAME)
    except PackageNotFoundError:
        pass

    # Try reading pyproject.toml from source tree (development mode)
    try:
        # Look for pyproject.toml in the project root
        # This assumes we're in a source checkout
        current_file = Path(__file__)
        # Navigate from src/get_gphotos_data/core/paths.py to project root
        project_root = current_file.parent.parent.parent.parent
        pyproject_path = project_root / "pyproject.toml"
        if pyproject_path.exists():
            import tomllib  # Python 3.11+

            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
                if "project" in data and "version" in data["project"]:
                    return data["project"]["version"]
    except Exception as e:
        log = logging.getLogger(__name__)
        log.debug("Could not read version from pyproject.toml: %s", e)

    return _DEFAULT_VERSION


def app_data_dir() -> Path:
    """Return a per-user app data directory for logs and settings."""
    return Path(user_data_dir(appname=APP_NAME, appauthor=APP_ORG, roaming=True))


def app_executable_dir() -> Path:
    """Return the directory where the application executable or script is located.
    
    For frozen executables (PyInstaller, etc.), returns the directory containing the executable.
    For scripts, returns the directory containing the main script.
    For development (running from virtual environment), returns the project root.
    
    Returns:
        Path to the application directory (project root in development)
    """
    import sys
    if getattr(sys, "frozen", False):
        # Running as compiled executable (PyInstaller, etc.)
        return Path(sys.executable).parent
    else:
        # Running as script
        main_module = sys.modules.get("__main__")
        if main_module and hasattr(main_module, "__file__"):
            script_dir = Path(main_module.__file__).parent
            
            # Check if we're running from a virtual environment (development mode)
            # If the script is in .venv/bin, .env/bin, venv/bin, or env/bin, go up to project root
            script_path_str = str(script_dir)
            if any(venv_path in script_path_str for venv_path in [".venv/bin", ".env/bin", "venv/bin", "env/bin"]):
                # Navigate from venv/bin to project root
                # Find the project root by looking for pyproject.toml
                current = script_dir
                for _ in range(10):  # Limit search to avoid infinite loops
                    if (current / "pyproject.toml").exists():
                        return current
                    parent = current.parent
                    if parent == current:  # Reached filesystem root
                        break
                    current = parent
                # If pyproject.toml not found, go up two levels from .venv/bin
                return script_dir.parent.parent
            
            return script_dir
        # Fallback to current working directory
        return Path.cwd()


def qss_text(theme: str = "light") -> str:
    """Return the bundled QSS stylesheet as text for the given theme."""
    filename = "styles_dark.qss" if theme == "dark" else "styles.qss"
    return (files("get_gphotos_data") / _ASSETS_DIR / filename).read_text(encoding="utf-8")


def app_icon_bytes() -> bytes:
    """Return the bundled app icon as PNG bytes."""
    return (files("get_gphotos_data") / _ASSETS_DIR / "app_icon.png").read_bytes()
