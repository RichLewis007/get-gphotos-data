# get-gphotos-data

A Python desktop app to pull Google Photos data from their API.

**Author:** Rich Lewis - GitHub: [@RichLewis007](https://github.com/RichLewis007)

## Features

## Requirements

- Python 3.13.11 (max version allowed, as it is highest version supported by our PySide 6 v6.7.3 which in turn is the highest version which supports my macOS 12.7.6)
- uv

## Run

```bash
uv sync --dev
uv run get-gphotos-data
```

`uv sync --dev` creates or updates the local `.venv/` and `uv.lock` as needed.

Note: the distribution name is `get-gphotos-data`, while the importable package
module remains `get_gphotos_data` so the repo folder name can differ safely.

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
uv run pyright
```

## Build

```bash
uv build
```

The wheel bundles the `assets/` directory, and the app loads them via `importlib.resources`
so themes and icons work when installed.

## Documentation



See also:

- `CHANGELOG.md` - Complete list of features, changes, and fixes
- `local/notes.md` - Development notes and feature checklist

See source code docstrings for detailed implementation documentation.
All modules include comprehensive top-of-file and inline comments explaining:

- Module purpose and functionality
- Class and function responsibilities
- Parameter descriptions
- Implementation details and design decisions

## Where to start

- `src/get_gphotos_data/app.py` - app startup, logging, resource loading
- `src/get_gphotos_data/main_window.py` - menus, widgets, signals, actions
- `src/get_gphotos_data/core/settings.py` - settings keys and defaults
- `src/get_gphotos_data/core/logging_setup.py` - log path and logging format
- `src/get_gphotos_data/core/workers.py` - background task pattern
- `src/get_gphotos_data/core/paths.py` - app data paths and bundled assets
- `src/get_gphotos_data/assets/ui/` - Qt Designer .ui files for the GUI
