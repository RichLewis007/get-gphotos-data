"""Google Photos OAuth 2.0 authentication.

This module handles OAuth 2.0 authentication flow for Google Photos API,
including credential storage and token refresh.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ..core.paths import app_data_dir

# Google Photos API scopes
# Note: photoslibrary.readonly was deprecated March 31, 2025, but still works
# and is needed to access ALL photos (not just app-created data)
# See local/scope-change-notes.md for details
SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
]

# Token file name (stored in app data directory)
TOKEN_FILE = "google_photos_token.json"


class GooglePhotosAuth:
    """Manages OAuth 2.0 authentication for Google Photos API."""

    def __init__(self, credentials_path: Path | str) -> None:
        """Initialize the authentication handler.

        Args:
            credentials_path: Path to the OAuth 2.0 credentials JSON file
                             (downloaded from Google Cloud Console)
        """
        self.log = logging.getLogger(__name__)
        self.credentials_path = Path(credentials_path)
        self.token_path = app_data_dir() / TOKEN_FILE
        self.credentials: Credentials | None = None

    def authenticate(self) -> Credentials:
        """Authenticate and return credentials.

        Loads existing credentials if available, otherwise starts OAuth flow.
        Automatically refreshes expired tokens.

        Returns:
            Valid OAuth 2.0 credentials

        Raises:
            FileNotFoundError: If credentials file is not found
            Exception: If authentication fails
        """
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_path}\n"
                "Please download credentials from Google Cloud Console and place them "
                "in the project directory. See README.md for instructions."
            )

        # Try to load existing token
        if self.token_path.exists():
            try:
                self.credentials = Credentials.from_authorized_user_file(
                    str(self.token_path), SCOPES
                )
                self.log.info("Loaded existing credentials from %s", self.token_path)
            except Exception as e:
                self.log.warning("Failed to load credentials: %s", e)
                self.credentials = None

        # If no valid credentials, start OAuth flow
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                # Try to refresh
                try:
                    self.credentials.refresh(Request())
                    self.log.info("Refreshed expired credentials")
                except Exception as e:
                    self.log.warning("Failed to refresh credentials: %s", e)
                    self.credentials = None

            if not self.credentials or not self.credentials.valid:
                # Start new OAuth flow
                self._run_oauth_flow()

        # Save credentials for next time
        if self.credentials and self.credentials.valid:
            self._save_credentials()

        if not self.credentials:
            raise RuntimeError("Authentication failed: no credentials obtained")
        return self.credentials

    def _run_oauth_flow(self) -> None:
        """Run the OAuth 2.0 flow to obtain new credentials."""
        self.log.info("Starting OAuth 2.0 flow...")
        flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        # Type assertion: run_local_server returns Credentials
        self.credentials = creds  # type: ignore[assignment]
        self.log.info("OAuth flow completed successfully")

    def _save_credentials(self) -> None:
        """Save credentials to token file."""
        if not self.credentials:
            return

        # Ensure app data directory exists
        self.token_path.parent.mkdir(parents=True, exist_ok=True)

        # Save credentials
        token_data: dict[str, Any] = {
            "token": self.credentials.token,
            "refresh_token": self.credentials.refresh_token,
            "token_uri": self.credentials.token_uri,
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret,
            "scopes": self.credentials.scopes,
        }

        with self.token_path.open("w") as f:
            json.dump(token_data, f, indent=2)

        self.log.info("Saved credentials to %s", self.token_path)

    def is_authenticated(self) -> bool:
        """Check if valid credentials are available."""
        if not self.credentials:
            return False
        if not self.credentials.valid:
            if self.credentials.expired and self.credentials.refresh_token:
                try:
                    self.credentials.refresh(Request())
                    return True
                except Exception:
                    return False
            return False
        return True

    def revoke(self) -> None:
        """Revoke credentials and delete token file."""
        if self.credentials:
            try:
                # Check if revoke method exists (not all credential types have it)
                if hasattr(self.credentials, "revoke"):
                    self.credentials.revoke(Request())  # type: ignore[attr-defined]
            except Exception as e:
                self.log.warning("Failed to revoke credentials: %s", e)

        if self.token_path.exists():
            self.token_path.unlink()
            self.log.info("Deleted token file: %s", self.token_path)

        self.credentials = None
