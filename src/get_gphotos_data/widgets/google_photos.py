"""Google Photos data viewer widget.

This widget displays Google Photos data retrieved from the API,
including media items, albums, and shared albums.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.paths import app_data_dir, app_executable_dir
from ..core.ui_loader import load_ui
from ..core.workers import WorkContext, WorkRequest, Worker, WorkerPool
from ..photos.auth import GooglePhotosAuth
from ..photos.client import GooglePhotosClient

# Token file name (same as in auth.py)
TOKEN_FILE = "google_photos_token.json"


class GooglePhotosView(QWidget):
    """Widget for viewing Google Photos data from the API."""

    # Signal emitted when authentication status changes
    authenticated_changed = Signal(bool)

    def __init__(self, parent=None, debug_api: bool = False) -> None:
        """Initialize the Google Photos viewer widget.

        Args:
            parent: Parent widget
            debug_api: If True, enable detailed API logging to console
        """
        super().__init__(parent)
        self.log = logging.getLogger(__name__)
        self.debug_api = debug_api
        
        # Load UI from .ui file
        ui_widget = load_ui("google_photos_view.ui", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(ui_widget)

        # Find widgets
        auth_status_label = ui_widget.findChild(QLabel, "authStatusLabel")
        if auth_status_label is None:
            raise RuntimeError("authStatusLabel not found in google_photos_view.ui")
        self.auth_status_label = cast(QLabel, auth_status_label)
            
        authenticate_button = ui_widget.findChild(QPushButton, "authenticateButton")
        if authenticate_button is None:
            raise RuntimeError("authenticateButton not found in google_photos_view.ui")
        self.authenticate_button = cast(QPushButton, authenticate_button)
            
        refresh_button = ui_widget.findChild(QPushButton, "refreshButton")
        if refresh_button is None:
            raise RuntimeError("refreshButton not found in google_photos_view.ui")
        self.refresh_button = cast(QPushButton, refresh_button)
            
        data_tabs = ui_widget.findChild(QTabWidget, "dataTabs")
        if data_tabs is None:
            raise RuntimeError("dataTabs not found in google_photos_view.ui")
        self.data_tabs = cast(QTabWidget, data_tabs)
        
        # Media Items tab
        media_items_count_label = ui_widget.findChild(QLabel, "mediaItemsCountLabel")
        if media_items_count_label is None:
            raise RuntimeError("mediaItemsCountLabel not found in google_photos_view.ui")
        self.media_items_count_label = cast(QLabel, media_items_count_label)
            
        media_items_table = ui_widget.findChild(QTableWidget, "mediaItemsTable")
        if media_items_table is None:
            raise RuntimeError("mediaItemsTable not found in google_photos_view.ui")
        self.media_items_table = cast(QTableWidget, media_items_table)
        
        # Albums tab
        albums_count_label = ui_widget.findChild(QLabel, "albumsCountLabel")
        if albums_count_label is None:
            raise RuntimeError("albumsCountLabel not found in google_photos_view.ui")
        self.albums_count_label = cast(QLabel, albums_count_label)
            
        albums_table = ui_widget.findChild(QTableWidget, "albumsTable")
        if albums_table is None:
            raise RuntimeError("albumsTable not found in google_photos_view.ui")
        self.albums_table = cast(QTableWidget, albums_table)
        
        # Shared Albums tab
        shared_albums_count_label = ui_widget.findChild(QLabel, "sharedAlbumsCountLabel")
        if shared_albums_count_label is None:
            raise RuntimeError("sharedAlbumsCountLabel not found in google_photos_view.ui")
        self.shared_albums_count_label = cast(QLabel, shared_albums_count_label)
            
        shared_albums_table = ui_widget.findChild(QTableWidget, "sharedAlbumsTable")
        if shared_albums_table is None:
            raise RuntimeError("sharedAlbumsTable not found in google_photos_view.ui")
        self.shared_albums_table = cast(QTableWidget, shared_albums_table)
        
        # Details tab
        details_text = ui_widget.findChild(QTextEdit, "detailsText")
        if details_text is None:
            raise RuntimeError("detailsText not found in google_photos_view.ui")
        self.details_text = cast(QTextEdit, details_text)

        # Connect signals
        self.authenticate_button.clicked.connect(self.on_authenticate)
        self.refresh_button.clicked.connect(self.on_refresh_data)
        
        # Connect table selection changes to show details
        self.media_items_table.itemSelectionChanged.connect(self.on_media_item_selected)
        self.albums_table.itemSelectionChanged.connect(self.on_album_selected)
        self.shared_albums_table.itemSelectionChanged.connect(self.on_shared_album_selected)

        # Initialize state
        self.auth: GooglePhotosAuth | None = None
        self.client: GooglePhotosClient | None = None
        self.media_items: list[dict[str, Any]] = []
        self.albums: list[dict[str, Any]] = []
        self.shared_albums: list[dict[str, Any]] = []
        self.pool = WorkerPool()
        self.active_worker: Worker[tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]] | None = None

        # Disable authenticate button by default
        self.authenticate_button.setEnabled(False)
        
        self._update_ui_state(False)

        # Try to load credentials.json from program's directory
        # This will enable the authenticate button if credentials.json is not found
        self._try_load_credentials()

    def set_credentials_path(self, credentials_path: Path | str) -> None:
        """Set the path to the OAuth credentials file.

        Args:
            credentials_path: Path to credentials.json file
        """
        self.auth = GooglePhotosAuth(credentials_path)
        # Check if already authenticated
        if self.auth.is_authenticated():
            try:
                credentials = self.auth.authenticate()
                self.client = GooglePhotosClient(credentials, debug=self.debug_api)
                self._update_ui_state(True)
            except Exception as e:
                self.log.warning("Failed to initialize authenticated client: %s", e)
                self._update_ui_state(False)

    def _update_ui_state(self, authenticated: bool) -> None:
        """Update UI based on authentication state.

        Args:
            authenticated: Whether user is authenticated
        """
        if authenticated:
            self.auth_status_label.setText("Authenticated")
            self.authenticate_button.setText("Re-authenticate")
            self.authenticate_button.setEnabled(True)
            self.refresh_button.setEnabled(True)
        else:
            self.auth_status_label.setText("Not authenticated")
            self.authenticate_button.setText("Authenticate")
            # Don't disable authenticate button here - let _try_load_credentials handle it
            self.refresh_button.setEnabled(False)
            # Clear data
            self._clear_all_tables()

        self.authenticated_changed.emit(authenticated)

    def _try_load_credentials(self) -> None:
        """Try to load credentials.json from the program's directory.
        
        If credentials.json is found and a token file exists, attempts to authenticate automatically.
        If not found or authentication fails, enables the authenticate button.
        """
        app_dir = app_executable_dir()
        credentials_path = app_dir / "credentials.json"
        token_path = app_data_dir() / TOKEN_FILE
        
        if credentials_path.exists():
            self.log.info("Found credentials.json in program directory: %s", credentials_path)
            # Only auto-authenticate if a token file exists (user has authenticated before)
            if token_path.exists():
                try:
                    # Create auth instance and attempt to authenticate
                    self.auth = GooglePhotosAuth(credentials_path)
                    # Try to authenticate (will load existing token and refresh if needed)
                    credentials = self.auth.authenticate()
                    # If we got here, authentication succeeded
                    self.client = GooglePhotosClient(credentials, debug=self.debug_api)
                    self._update_ui_state(True)
                    self.log.info("Successfully authenticated with existing credentials")
                except Exception as e:
                    # Authentication failed - user may need to re-authenticate
                    self.log.warning("Failed to authenticate automatically: %s", e)
                    self.auth = GooglePhotosAuth(credentials_path)  # Keep auth instance for manual auth
                    self.client = None
                    self._update_ui_state(False)
                    self.authenticate_button.setEnabled(True)
            else:
                # Credentials file exists but no token - user needs to authenticate for first time
                self.log.info("credentials.json found but no token file - user needs to authenticate")
                self.auth = GooglePhotosAuth(credentials_path)
                self.authenticate_button.setEnabled(True)
        else:
            self.log.info("credentials.json not found in program directory: %s", app_dir)
            # Enable authenticate button if credentials file not found
            self.authenticate_button.setEnabled(True)

    def on_authenticate(self) -> None:
        """Handle authenticate button click."""
        if self.auth is None:
            # Prompt for credentials file
            credentials_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Google Photos Credentials File",
                str(Path.home()),
                "JSON Files (*.json);;All Files (*)",
            )
            if not credentials_path:
                return
            self.auth = GooglePhotosAuth(credentials_path)

        try:
            credentials = self.auth.authenticate()
            self.client = GooglePhotosClient(credentials, debug=self.debug_api)
            self._update_ui_state(True)
            QMessageBox.information(self, "Authentication", "Successfully authenticated with Google Photos!")
            # Automatically refresh data after authentication
            self.on_refresh_data()
        except FileNotFoundError as e:
            QMessageBox.critical(self, "Authentication Error", f"Credentials file not found:\n{e}")
        except Exception as e:
            self.log.exception("Authentication failed")
            QMessageBox.critical(self, "Authentication Error", f"Failed to authenticate:\n{e}")

    def on_refresh_data(self) -> None:
        """Refresh data from Google Photos API using a background worker.
        
        Fetches a single page of data for quick testing.
        """
        if not self.client:
            QMessageBox.warning(self, "Not Authenticated", "Please authenticate first.")
            return

        if self.active_worker is not None:
            QMessageBox.information(self, "Loading", "Data is already being loaded. Please wait.")
            return

        # Store client in local variable for type narrowing in nested function
        client = self.client
        assert client is not None  # Type narrowing

        # Create progress dialog
        progress_dialog = QProgressDialog("Loading data from Google Photos...", "Cancel", 0, 100, self)
        progress_dialog.setWindowTitle("Loading Google Photos Data")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)  # Show immediately
        progress_dialog.setValue(0)

        # Show progress
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Loading...")

        def work(ctx: WorkContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
            """Background work function - runs in worker thread.
            
            Fetches a single page of data from the Google Photos API.
            """
            # Fetch media items (single page)
            ctx.progress(10, "Fetching media items...")
            ctx.check_cancelled()
            media_response = client.list_media_items(page_size=100)
            media_items = media_response.get("mediaItems", [])
            
            # Fetch albums (single page)
            ctx.progress(50, "Fetching albums...")
            ctx.check_cancelled()
            albums_response = client.list_albums(page_size=50)
            albums = albums_response.get("albums", [])
            
            # Fetch shared albums (single page)
            ctx.progress(90, "Fetching shared albums...")
            ctx.check_cancelled()
            shared_albums_response = client.list_shared_albums(page_size=50)
            shared_albums = shared_albums_response.get("sharedAlbums", [])
            
            ctx.progress(100, "Complete")
            return (media_items, albums, shared_albums)

        def progress(percent: int, message: str) -> None:
            """Progress callback - runs on main thread via signal."""
            progress_dialog.setValue(percent)
            if message:
                progress_dialog.setLabelText(message)
                self.refresh_button.setText(message)
            # Process events to update UI
            progress_dialog.show()

        def done(result: tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]) -> None:
            """Completion callback - runs on main thread when worker finishes."""
            progress_dialog.close()
            
            media_items, albums, shared_albums = result
            
            # Update data
            self.media_items = media_items
            self.albums = albums
            self.shared_albums = shared_albums
            
            # Populate tables
            self._populate_media_items_table()
            self._populate_albums_table()
            self._populate_shared_albums_table()
            
            # Show completion message
            QMessageBox.information(
                self,
                "Data Refreshed",
                f"Loaded {len(self.media_items)} media items, "
                f"{len(self.albums)} albums, and {len(self.shared_albums)} shared albums.\n\n"
                "Note: This is a single page of results. Use 'Load All' to fetch all data.",
            )
            
            # Reset UI
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Refresh Data")
            self.active_worker = None
            self.log.info("Data refresh completed")

        def cancelled() -> None:
            """Cancellation callback - runs on main thread when work is cancelled."""
            progress_dialog.close()
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Refresh Data")
            self.active_worker = None
            self.log.info("Data refresh cancelled")

        def error(msg: str) -> None:
            """Error callback - runs on main thread when work fails."""
            progress_dialog.close()
            error_msg = msg
            # Provide helpful guidance for 403 errors
            if "403" in error_msg or "Forbidden" in error_msg:
                error_msg = (
                    f"403 Forbidden Error:\n{error_msg}\n\n"
                    "This usually means:\n"
                    "1. The Google Photos Library API is not enabled in your Google Cloud Console\n"
                    "   → Go to APIs & Services > Library > Enable 'Google Photos Library API'\n"
                    "2. The OAuth scope was not granted during authentication\n"
                    "   → Try re-authenticating and make sure to grant all permissions\n"
                    "3. The scope is not added to your OAuth consent screen\n"
                    "   → Add 'https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata' to scopes"
                )
            QMessageBox.critical(self, "Error", error_msg)
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Refresh Data")
            self.active_worker = None
            self.log.exception("Failed to refresh data")

        # Connect cancel button to worker cancellation
        def cancel_work() -> None:
            if self.active_worker is not None:
                self.active_worker.cancel()

        progress_dialog.canceled.connect(cancel_work)

        req = WorkRequest(
            fn=work,
            on_done=done,
            on_error=error,
            on_progress=progress,
            on_cancel=cancelled,
        )
        self.active_worker = self.pool.submit(req)

    def _clear_all_tables(self) -> None:
        """Clear all data tables."""
        self.media_items_table.setRowCount(0)
        self.albums_table.setRowCount(0)
        self.shared_albums_table.setRowCount(0)
        self.media_items_count_label.setText("0 media items")
        self.albums_count_label.setText("0 albums")
        self.shared_albums_count_label.setText("0 shared albums")
        self.details_text.clear()

    def _populate_media_items_table(self) -> None:
        """Populate the media items table."""
        self.media_items_table.setRowCount(len(self.media_items))
        self.media_items_count_label.setText(f"{len(self.media_items)} media items")

        for row, item in enumerate(self.media_items):
            # ID
            id_item = QTableWidgetItem(item.get("id", ""))
            id_item.setData(Qt.ItemDataRole.UserRole, item)  # Store full item data
            self.media_items_table.setItem(row, 0, id_item)

            # Filename
            filename_item = QTableWidgetItem(item.get("filename", ""))
            self.media_items_table.setItem(row, 1, filename_item)

            # MIME Type
            mime_item = QTableWidgetItem(item.get("mimeType", ""))
            self.media_items_table.setItem(row, 2, mime_item)

            # Created time
            metadata = item.get("mediaMetadata", {})
            created_item = QTableWidgetItem(metadata.get("creationTime", ""))
            self.media_items_table.setItem(row, 3, created_item)

            # Dimensions
            width = metadata.get("width", "")
            height = metadata.get("height", "")
            dims_item = QTableWidgetItem(f"{width} × {height}" if width and height else "")
            self.media_items_table.setItem(row, 4, dims_item)

        # Resize columns to content
        self.media_items_table.resizeColumnsToContents()

    def _populate_albums_table(self) -> None:
        """Populate the albums table."""
        self.albums_table.setRowCount(len(self.albums))
        self.albums_count_label.setText(f"{len(self.albums)} albums")

        for row, album in enumerate(self.albums):
            # ID
            id_item = QTableWidgetItem(album.get("id", ""))
            id_item.setData(Qt.ItemDataRole.UserRole, album)  # Store full album data
            self.albums_table.setItem(row, 0, id_item)

            # Title
            title_item = QTableWidgetItem(album.get("title", ""))
            self.albums_table.setItem(row, 1, title_item)

            # Items count
            count_item = QTableWidgetItem(str(album.get("mediaItemsCount", 0)))
            self.albums_table.setItem(row, 2, count_item)

            # Writeable
            writeable_item = QTableWidgetItem("Yes" if album.get("isWriteable", False) else "No")
            self.albums_table.setItem(row, 3, writeable_item)

        # Resize columns to content
        self.albums_table.resizeColumnsToContents()

    def _populate_shared_albums_table(self) -> None:
        """Populate the shared albums table."""
        self.shared_albums_table.setRowCount(len(self.shared_albums))
        self.shared_albums_count_label.setText(f"{len(self.shared_albums)} shared albums")

        for row, album in enumerate(self.shared_albums):
            # ID
            id_item = QTableWidgetItem(album.get("id", ""))
            id_item.setData(Qt.ItemDataRole.UserRole, album)  # Store full album data
            self.shared_albums_table.setItem(row, 0, id_item)

            # Title
            title_item = QTableWidgetItem(album.get("title", ""))
            self.shared_albums_table.setItem(row, 1, title_item)

            # Items count
            count_item = QTableWidgetItem(str(album.get("mediaItemsCount", 0)))
            self.shared_albums_table.setItem(row, 2, count_item)

            # Writeable
            writeable_item = QTableWidgetItem("Yes" if album.get("isWriteable", False) else "No")
            self.shared_albums_table.setItem(row, 3, writeable_item)

        # Resize columns to content
        self.shared_albums_table.resizeColumnsToContents()

    def on_media_item_selected(self) -> None:
        """Handle media item selection to show details."""
        selected_items = self.media_items_table.selectedItems()
        if not selected_items:
            return

        # Get the first selected row's data
        row = selected_items[0].row()
        id_item = self.media_items_table.item(row, 0)
        if id_item:
            item_data = id_item.data(Qt.ItemDataRole.UserRole)
            if item_data:
                self._show_item_details(item_data, "Media Item")

    def on_album_selected(self) -> None:
        """Handle album selection to show details."""
        selected_items = self.albums_table.selectedItems()
        if not selected_items:
            return

        # Get the first selected row's data
        row = selected_items[0].row()
        id_item = self.albums_table.item(row, 0)
        if id_item:
            album_data = id_item.data(Qt.ItemDataRole.UserRole)
            if album_data:
                self._show_item_details(album_data, "Album")

    def on_shared_album_selected(self) -> None:
        """Handle shared album selection to show details."""
        selected_items = self.shared_albums_table.selectedItems()
        if not selected_items:
            return

        # Get the first selected row's data
        row = selected_items[0].row()
        id_item = self.shared_albums_table.item(row, 0)
        if id_item:
            album_data = id_item.data(Qt.ItemDataRole.UserRole)
            if album_data:
                self._show_item_details(album_data, "Shared Album")

    def _show_item_details(self, data: dict[str, Any], item_type: str) -> None:
        """Show detailed JSON view of the selected item.

        Args:
            data: The item data dictionary
            item_type: Type of item (for display)
        """
        # Switch to details tab
        self.data_tabs.setCurrentIndex(3)  # Details tab is index 3

        # Format JSON with indentation
        try:
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            self.details_text.setPlainText(f"{item_type} Details:\n\n{json_str}")
        except Exception as e:
            self.log.error("Failed to format details: %s", e)
            self.details_text.setPlainText(f"Error displaying {item_type} details:\n{e}")
