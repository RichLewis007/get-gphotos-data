"""Google Photos data viewer widget.

This widget displays Google Photos data retrieved from the API,
including media items, albums, and shared albums.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.ui_loader import load_ui
from ..photos.auth import GooglePhotosAuth
from ..photos.client import GooglePhotosClient


class GooglePhotosView(QWidget):
    """Widget for viewing Google Photos data from the API."""

    # Signal emitted when authentication status changes
    authenticated_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.log = logging.getLogger(__name__)
        
        # Load UI from .ui file
        ui_widget = load_ui("google_photos_view.ui", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(ui_widget)

        # Find widgets
        self.auth_status_label = ui_widget.findChild(QLabel, "authStatusLabel")
        if self.auth_status_label is None:
            raise RuntimeError("authStatusLabel not found in google_photos_view.ui")
            
        self.authenticate_button = ui_widget.findChild(QPushButton, "authenticateButton")
        if self.authenticate_button is None:
            raise RuntimeError("authenticateButton not found in google_photos_view.ui")
            
        self.refresh_button = ui_widget.findChild(QPushButton, "refreshButton")
        if self.refresh_button is None:
            raise RuntimeError("refreshButton not found in google_photos_view.ui")
            
        self.data_tabs = ui_widget.findChild(QTabWidget, "dataTabs")
        if self.data_tabs is None:
            raise RuntimeError("dataTabs not found in google_photos_view.ui")
        
        # Media Items tab
        self.media_items_count_label = ui_widget.findChild(QLabel, "mediaItemsCountLabel")
        if self.media_items_count_label is None:
            raise RuntimeError("mediaItemsCountLabel not found in google_photos_view.ui")
            
        self.media_items_table = ui_widget.findChild(QTableWidget, "mediaItemsTable")
        if self.media_items_table is None:
            raise RuntimeError("mediaItemsTable not found in google_photos_view.ui")
        
        # Albums tab
        self.albums_count_label = ui_widget.findChild(QLabel, "albumsCountLabel")
        if self.albums_count_label is None:
            raise RuntimeError("albumsCountLabel not found in google_photos_view.ui")
            
        self.albums_table = ui_widget.findChild(QTableWidget, "albumsTable")
        if self.albums_table is None:
            raise RuntimeError("albumsTable not found in google_photos_view.ui")
        
        # Shared Albums tab
        self.shared_albums_count_label = ui_widget.findChild(QLabel, "sharedAlbumsCountLabel")
        if self.shared_albums_count_label is None:
            raise RuntimeError("sharedAlbumsCountLabel not found in google_photos_view.ui")
            
        self.shared_albums_table = ui_widget.findChild(QTableWidget, "sharedAlbumsTable")
        if self.shared_albums_table is None:
            raise RuntimeError("sharedAlbumsTable not found in google_photos_view.ui")
        
        # Details tab
        self.details_text = ui_widget.findChild(QTextEdit, "detailsText")
        if self.details_text is None:
            raise RuntimeError("detailsText not found in google_photos_view.ui")

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

        self._update_ui_state(False)

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
                self.client = GooglePhotosClient(credentials)
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
            self.refresh_button.setEnabled(True)
        else:
            self.auth_status_label.setText("Not authenticated")
            self.authenticate_button.setText("Authenticate")
            self.refresh_button.setEnabled(False)
            # Clear data
            self._clear_all_tables()

        self.authenticated_changed.emit(authenticated)

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
            self.client = GooglePhotosClient(credentials)
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
        """Refresh all data from Google Photos API."""
        if not self.client:
            QMessageBox.warning(self, "Not Authenticated", "Please authenticate first.")
            return

        try:
            # Show progress
            self.refresh_button.setEnabled(False)
            self.refresh_button.setText("Loading...")

            # Fetch media items
            self.log.info("Fetching media items...")
            self.media_items = self.client.get_all_media_items()
            self._populate_media_items_table()

            # Fetch albums
            self.log.info("Fetching albums...")
            self.albums = self.client.get_all_albums()
            self._populate_albums_table()

            # Fetch shared albums
            self.log.info("Fetching shared albums...")
            self.shared_albums = self.client.get_all_shared_albums()
            self._populate_shared_albums_table()

            QMessageBox.information(
                self,
                "Data Refreshed",
                f"Loaded {len(self.media_items)} media items, "
                f"{len(self.albums)} albums, and {len(self.shared_albums)} shared albums.",
            )
        except Exception as e:
            self.log.exception("Failed to refresh data")
            QMessageBox.critical(self, "Error", f"Failed to refresh data:\n{e}")
        finally:
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Refresh Data")

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
