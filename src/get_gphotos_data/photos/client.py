"""Google Photos Library API client using requests.

This module provides a client for accessing the Google Photos Library API
using the requests library. It handles all API endpoints and data retrieval.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from google.oauth2.credentials import Credentials

# Google Photos API base URL
API_BASE_URL = "https://photoslibrary.googleapis.com/v1"


class GooglePhotosClient:
    """Client for Google Photos Library API using requests library."""

    def __init__(self, credentials: Credentials, debug: bool = False) -> None:
        """Initialize the API client.

        Args:
            credentials: OAuth 2.0 credentials from GooglePhotosAuth
            debug: If True, log detailed API request/response information
        """
        self.log = logging.getLogger(__name__)
        self.credentials = credentials
        self.debug = debug
        self.session = requests.Session()
        self._update_session_auth()

    def _update_session_auth(self) -> None:
        """Update session with current credentials."""
        if not self.credentials.valid:
            if self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(requests.Request())
            else:
                raise ValueError("Credentials are invalid and cannot be refreshed")

        # Set Authorization header
        self.session.headers.update(
            {"Authorization": f"Bearer {self.credentials.token}"}
        )

    def _request(
        self, method: str, endpoint: str, params: dict[str, Any] | None = None, json_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an API request and return JSON response.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON body data

        Returns:
            JSON response as dictionary

        Raises:
            requests.RequestException: If the request fails
        """
        url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
        
        # Ensure credentials are valid
        self._update_session_auth()

        # Log request if debug is enabled
        if self.debug:
            self.log.info("API Request: %s %s", method, url)
            if params:
                self.log.info("  Params: %s", params)
            if json_data:
                self.log.info("  JSON Body: %s", json_data)

        try:
            response = self.session.request(
                method=method, url=url, params=params, json=json_data, timeout=30
            )
            
            response.raise_for_status()
            response_json = response.json()
            
            # Log response if debug is enabled
            if self.debug:
                self.log.info("API Response: %s %s - Status: %s", method, url, response.status_code)
                # Log response size for large responses
                if isinstance(response_json, dict):
                    if "mediaItems" in response_json:
                        count = len(response_json.get("mediaItems", []))
                        self.log.info("  Response contains %d media items", count)
                    elif "albums" in response_json:
                        count = len(response_json.get("albums", []))
                        self.log.info("  Response contains %d albums", count)
                    elif "sharedAlbums" in response_json:
                        count = len(response_json.get("sharedAlbums", []))
                        self.log.info("  Response contains %d shared albums", count)
            
            return response_json
        except requests.HTTPError as e:
            # HTTPError is raised by raise_for_status(), so response should exist
            # Provide more detailed error information for 403 errors
            if e.response is not None and e.response.status_code == 403:
                error_detail = ""
                try:
                    error_json = e.response.json()
                    error_detail = error_json.get("error", {}).get("message", "")
                    if error_detail:
                        error_detail = f"\nError details: {error_detail}"
                except Exception:
                    pass
                self.log.error(
                    "API request forbidden (403): %s %s%s\n"
                    "Common causes:\n"
                    "1. Google Photos Library API not enabled in Google Cloud Console\n"
                    "2. OAuth scope not granted or not in consent screen\n"
                    "3. Insufficient permissions",
                    method,
                    url,
                    error_detail,
                )
            else:
                self.log.error("API request failed: %s %s - %s", method, url, e)
            raise
        except requests.RequestException as e:
            self.log.error("API request failed: %s %s - %s", method, url, e)
            raise

    # Media Items Methods

    def list_media_items(
        self, page_size: int = 25, page_token: str | None = None
    ) -> dict[str, Any]:
        """List media items.

        Args:
            page_size: Maximum number of media items to return (max 100)
            page_token: Token for pagination

        Returns:
            Response containing mediaItems and nextPageToken
        """
        params: dict[str, Any] = {"pageSize": min(page_size, 100)}
        if page_token:
            params["pageToken"] = page_token

        return self._request("GET", "mediaItems", params=params)

    def get_media_item(self, media_item_id: str) -> dict[str, Any]:
        """Get a specific media item by ID.

        Args:
            media_item_id: The media item ID

        Returns:
            Media item object
        """
        return self._request("GET", f"mediaItems/{media_item_id}")

    def search_media_items(
        self,
        album_id: str | None = None,
        page_size: int = 25,
        page_token: str | None = None,
        date_filter: dict[str, Any] | None = None,
        content_filter: dict[str, Any] | None = None,
        media_type_filter: dict[str, Any] | None = None,
        include_archived_media: bool = False,
        exclude_non_app_created_data: bool = False,
    ) -> dict[str, Any]:
        """Search for media items with filters.

        Args:
            album_id: Search within a specific album
            page_size: Maximum results per page
            page_token: Token for pagination
            date_filter: Filter by date range
            content_filter: Filter by content categories
            media_type_filter: Filter by media type (PHOTO, VIDEO)
            include_archived_media: Include archived items
            exclude_non_app_created_data: Exclude non-app-created data

        Returns:
            Response containing mediaItems and nextPageToken
        """
        request_body: dict[str, Any] = {
            "pageSize": min(page_size, 100),
            "includeArchivedMedia": include_archived_media,
            "excludeNonAppCreatedData": exclude_non_app_created_data,
        }

        if album_id:
            request_body["albumId"] = album_id
        if page_token:
            request_body["pageToken"] = page_token
        if date_filter:
            request_body["filters"] = request_body.get("filters", {})
            request_body["filters"]["dateFilter"] = date_filter
        if content_filter:
            request_body["filters"] = request_body.get("filters", {})
            request_body["filters"]["contentFilter"] = content_filter
        if media_type_filter:
            request_body["filters"] = request_body.get("filters", {})
            request_body["filters"]["mediaTypeFilter"] = media_type_filter

        return self._request("POST", "mediaItems:search", json_data=request_body)

    def get_all_media_items(
        self, page_size: int = 100
    ) -> list[dict[str, Any]]:
        """Get all media items (handles pagination automatically).

        Args:
            page_size: Number of items per page

        Returns:
            List of all media items
        """
        all_items: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            response = self.list_media_items(page_size=page_size, page_token=page_token)
            items = response.get("mediaItems", [])
            all_items.extend(items)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return all_items

    # Albums Methods

    def list_albums(
        self, page_size: int = 20, page_token: str | None = None
    ) -> dict[str, Any]:
        """List albums.

        Args:
            page_size: Maximum number of albums to return (max 50)
            page_token: Token for pagination

        Returns:
            Response containing albums and nextPageToken
        """
        params: dict[str, Any] = {"pageSize": min(page_size, 50)}
        if page_token:
            params["pageToken"] = page_token

        return self._request("GET", "albums", params=params)

    def get_album(self, album_id: str) -> dict[str, Any]:
        """Get a specific album by ID.

        Args:
            album_id: The album ID

        Returns:
            Album object
        """
        return self._request("GET", f"albums/{album_id}")

    def get_all_albums(self, page_size: int = 50) -> list[dict[str, Any]]:
        """Get all albums (handles pagination automatically).

        Args:
            page_size: Number of items per page

        Returns:
            List of all albums
        """
        all_albums: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            response = self.list_albums(page_size=page_size, page_token=page_token)
            albums = response.get("albums", [])
            all_albums.extend(albums)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return all_albums

    # Shared Albums Methods

    def list_shared_albums(
        self, page_size: int = 20, page_token: str | None = None
    ) -> dict[str, Any]:
        """List shared albums.

        Args:
            page_size: Maximum number of albums to return
            page_token: Token for pagination

        Returns:
            Response containing sharedAlbums and nextPageToken
        """
        params: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token

        return self._request("GET", "sharedAlbums", params=params)

    def get_all_shared_albums(self, page_size: int = 50) -> list[dict[str, Any]]:
        """Get all shared albums (handles pagination automatically).

        Args:
            page_size: Number of items per page

        Returns:
            List of all shared albums
        """
        all_albums: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            response = self.list_shared_albums(page_size=page_size, page_token=page_token)
            albums = response.get("sharedAlbums", [])
            all_albums.extend(albums)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return all_albums
