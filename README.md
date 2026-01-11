# get-gphotos-data

A Python desktop GUI application to access and view Google Photos data via their Library API.

**Author:** Rich Lewis - GitHub: [@RichLewis007](https://github.com/RichLewis007)

## Features

- **Google Photos Integration**: Access your Google Photos library through the official API
- **Comprehensive Data Viewing**: View media items, albums, and shared albums with detailed information
- **Modern GUI**: Built with PySide6 (Qt for Python) with an attractive, easy-to-use interface
- **Editable UI**: GUI layouts are defined in `.ui` files (Qt Designer format) for easy customization
- **REST API**: Uses the `requests` library directly for API calls (no third-party wrappers)
- **OAuth 2.0 Authentication**: Secure authentication with automatic token refresh
- **Detailed JSON View**: View full JSON data for any selected item

## Requirements

- Python 3.13.11 (max version allowed, as it is highest version supported by our PySide 6 v6.7.3 which in turn is the highest version which supports my macOS 12.7.6)
- uv (Python package manager)
- Google Cloud Project with Google Photos Library API enabled
- OAuth 2.0 credentials (see Authentication Setup below)

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/Google-Photos-Library-API.git
cd Google-Photos-Library-API

# Install dependencies
uv sync --dev

# Run the application
uv run get-gphotos-data
```

`uv sync --dev` creates or updates the local `.venv/` and `uv.lock` as needed.

Note: the distribution name is `get-gphotos-data`, while the importable package
module remains `get_gphotos_data` so the repo folder name can differ safely.

## Authentication Setup

To use this application, you need to set up OAuth 2.0 credentials with Google. Follow these steps:

### 1. Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Google Photos Library API**:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Photos Library API"
   - Click "Enable"

### 2. Create OAuth 2.0 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - Choose "Desktop" or "External" (unless you have a Google Workspace)
   - Fill in the required fields (App name, User support email, Developer contact)
   - Add scopes: `https://www.googleapis.com/auth/photoslibrary.readonly`
   - Add test users if needed (for external apps in testing mode)
4. Create OAuth client ID:
   - Application type: **Desktop app**
   - Name: "Google Photos Data Viewer" (or any name you prefer)
   - Click "Create"
5. Download the credentials:
   - Click the download icon next to your newly created OAuth client ID
   - Save the JSON file (e.g., `credentials.json`)
   - **Important**: Keep this file secure and do not commit it to version control

### 3. Place Credentials File

You have two options:

**Option A: Place in project directory (recommended for development)**

- Place `credentials.json` in the project root directory
- The file will be ignored by git (already in `.gitignore`)

**Option B: Use anywhere on your system**

- Store `credentials.json` anywhere on your system
- When you run the app and click "Authenticate", you'll be prompted to select the file

### 4. First-Time Authentication

1. Run the application: `uv run get-gphotos-data`
2. Go to the "Google Photos" tab
3. Click the "Authenticate" button
4. If you placed `credentials.json` in the project root, authentication will start automatically
   - Otherwise, you'll be prompted to select the credentials file
5. Your default web browser will open
6. Sign in with your Google account
7. Grant permissions to access your Google Photos library
8. The application will automatically save your authentication token for future use

### 5. Token Storage

- Authentication tokens are stored in your system's application data directory
- Tokens are automatically refreshed when they expire
- You can revoke access at any time through [Google Account Settings](https://myaccount.google.com/permissions)

## Usage

### Viewing Data

1. **Authenticate**: Click "Authenticate" if you haven't already
2. **Refresh Data**: Click "Refresh Data" to fetch your Google Photos data
3. **Browse Tabs**:
   - **Media Items**: View all photos and videos with metadata
   - **Albums**: View all albums created by the application
   - **Shared Albums**: View albums shared with you
   - **Item Details**: Select any item to see full JSON details

### Understanding the Data

**Note**: As of March 31, 2025, the Google Photos Library API only provides access to:

- Media items uploaded by your application
- Albums created by your application

To access your existing Google Photos, you would need to use the [Google Photos Picker API](https://developers.google.com/photos/picker) instead.

### Customizing the UI

The GUI is built using Qt Designer `.ui` files located in:

- `src/get_gphotos_data/assets/ui/google_photos_view.ui`

You can edit these files using Qt Designer or any text editor to customize the layout, styling, and widgets.

To open Qt Designer:

```bash
./qt-designer.sh  # If you have the script, or
designer  # If Qt Designer is in your PATH
```

## Development

### Running Tests

```bash
uv run pytest
```

### Code Quality

```bash
# Lint checking
uv run ruff check .

# Format code
uv run ruff format .

# Type checking
uv run pyright
```

### Development Server (with auto-reload)

```bash
uv run python scripts/dev.py
```

This starts the application with file watching - any changes to `.py` or `.ui` files will automatically restart the app.

## Build

```bash
uv build
```

The wheel bundles the `assets/` directory, and the app loads them via `importlib.resources`
so themes and icons work when installed.

## Project Structure

```
get-gphotos-data/
├── src/get_gphotos_data/
│   ├── photos/              # Google Photos API integration
│   │   ├── auth.py         # OAuth 2.0 authentication
│   │   └── client.py       # REST API client using requests
│   ├── widgets/
│   │   └── google_photos.py  # Google Photos viewer widget
│   ├── assets/ui/
│   │   └── google_photos_view.ui  # Qt Designer UI file
│   └── ...
├── API_REFERENCE.md        # Complete API documentation
├── README.md              # This file
└── pyproject.toml         # Project configuration
```

## Dependencies

- **PySide6**: Qt for Python (GUI framework)
- **requests**: HTTP library for API calls
- **google-auth**: Google authentication library
- **google-auth-oauthlib**: OAuth 2.0 flow helpers

See `pyproject.toml` for complete dependency list.

## Troubleshooting

### "Credentials file not found"

- Make sure you've downloaded the OAuth credentials JSON file
- Place it in the project root or select it when prompted
- Check that the file is named correctly (usually `credentials.json`)

### "Failed to authenticate"

- Check your internet connection
- Ensure the Google Photos Library API is enabled in your Google Cloud project
- Verify that you've granted the necessary permissions
- Check the application logs for detailed error messages

### "No data shown after authentication"

- Remember: The Library API only shows media items/albums created by your application
- If you haven't uploaded anything via the API, you won't see any media items
- Use "Refresh Data" to fetch the latest data

### Token refresh issues

- If tokens fail to refresh, try re-authenticating
- You can delete the token file (stored in your app data directory) and authenticate again
- Check that your OAuth credentials are still valid in Google Cloud Console

## Security Notes

- **Never commit** `credentials.json` to version control (it's already in `.gitignore`)
- Keep your OAuth credentials secure
- Authentication tokens are stored locally on your machine
- You can revoke access through Google Account Settings at any time

## API Documentation

For detailed information about the Google Photos Library API, see:

- `API_REFERENCE.md` - Complete reference of all available data and endpoints
- [Official Google Photos Library API Documentation](https://developers.google.com/photos/library/guides/overview)

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## See Also

- `CHANGELOG.md` - Complete list of features, changes, and fixes
- `local/notes.md` - Development notes and feature checklist
- `API_REFERENCE.md` - Complete Google Photos Library API reference

## Where to Start (Code)

- `src/get_gphotos_data/app.py` - app startup, logging, resource loading
- `src/get_gphotos_data/main_window.py` - menus, widgets, signals, actions
- `src/get_gphotos_data/photos/auth.py` - OAuth 2.0 authentication
- `src/get_gphotos_data/photos/client.py` - REST API client
- `src/get_gphotos_data/widgets/google_photos.py` - Google Photos viewer widget
- `src/get_gphotos_data/core/settings.py` - settings keys and defaults
- `src/get_gphotos_data/core/logging_setup.py` - log path and logging format
- `src/get_gphotos_data/core/workers.py` - background task pattern
- `src/get_gphotos_data/core/paths.py` - app data paths and bundled assets
- `src/get_gphotos_data/assets/ui/` - Qt Designer .ui files for the GUI

See source code docstrings for detailed implementation documentation.
All modules include comprehensive top-of-file and inline comments explaining:

- Module purpose and functionality
- Class and function responsibilities
- Parameter descriptions
- Implementation details and design decisions
