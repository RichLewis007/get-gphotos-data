"""Main application window implementation.

This module provides the main window class that implements:
- File management (open, recent files, drag-and-drop)
- Background worker execution with progress tracking
- Command palette integration
- Window state persistence (geometry and toolbar positions)
- System tray integration
- Theme-aware UI
- Log viewer panel

The UI layout is loaded from a Qt Designer .ui file, and widgets are
accessed programmatically for signal/slot connections.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Slot
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QPolygon,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QToolBar,
    QWidget,
)

from .core.constants import LOG_PREVIEW_BYTES, MAX_PREVIEW_BYTES
from .core.file_manager import FileManager
from .core.paths import APP_NAME, app_data_dir
from .core.settings import Settings
from .core.system_tray import SystemTray
from .core.ui_loader import load_ui
from .core.window_state import WindowStateManager
from .core.workers import WorkContext, Worker, WorkerPool, WorkRequest
from .dialogs.command_palette import Command, CommandPalette
from .dialogs.preferences import PreferencesDialog
from .widgets.calendar_demo import CalendarDemo
from .widgets.controls_demo import ControlsDemo
from .widgets.dialogs_demo import DialogsDemo
from .widgets.google_photos import GooglePhotosView
from .widgets.graphics_demo import GraphicsDemo
from .widgets.table_view_demo import TableViewDemo
from .widgets.text_editor_demo import TextEditorDemo
from .widgets.tree_view_demo import TreeViewDemo


class MainWindow(QMainWindow):
    """Main application window with comprehensive UI features and functionality."""

    def __init__(self, settings: Settings, instance_guard=None) -> None:
        super().__init__()
        self.log = logging.getLogger(__name__)
        self.settings = settings
        self.pool = WorkerPool()
        self.file_manager = FileManager(settings)
        self.window_state = WindowStateManager(settings, self)
        self.action_open: QAction
        self.action_work: QAction
        self.action_prefs: QAction
        self.action_quit: QAction
        self.action_about: QAction
        self.action_clear_recent: QAction
        self.recent_menu: QMenu
        self.active_worker: Worker[str] | None
        self.label: QLabel
        self.file_label: QLabel
        self.file_preview: QPlainTextEdit
        self.progress_bar: QProgressBar
        self.log_viewer: QPlainTextEdit
        self.btn_open: QPushButton
        self.btn_work: QPushButton
        self.btn_cancel: QPushButton
        self.btn_refresh_logs: QPushButton
        self.btn_prefs: QPushButton
        self.btn_minimize_to_tray: QPushButton
        self.ui: QWidget
        self.tray: SystemTray
        self.tab_widget: QTabWidget
        self.view_menu: QMenu

        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)

        self._build_actions()
        self._build_menus()  # Build menus before loading UI so dock widgets can add to View menu
        self._load_ui()
        self.active_worker = None

        # Create horizontal toolbar with square icon buttons
        toolbar = self._create_toolbar()
        self.addToolBar(toolbar)

        self.btn_work.clicked.connect(self.on_run_work)
        self.btn_cancel.clicked.connect(self.on_cancel_work)
        self.btn_prefs.clicked.connect(self.on_open_prefs)
        self.btn_open.clicked.connect(self.on_open_file)
        self.btn_refresh_logs.clicked.connect(self.on_refresh_logs)

        self._refresh_recent_menu()
        self.on_refresh_logs()

        # Restore window geometry and state
        self.window_state.restore_state()

        # Setup command palette
        self._setup_command_palette()

        # Setup system tray
        self.tray = SystemTray(self)
        if self.tray.is_available():
            self._setup_system_tray()
            # Show and enable minimize to tray button if tray is available
            if hasattr(self, "btn_minimize_to_tray"):
                self.btn_minimize_to_tray.setVisible(True)
                self.btn_minimize_to_tray.clicked.connect(self.on_minimize_to_tray)

    def _setup_system_tray(self) -> None:
        """Setup system tray integration."""
        from PySide6.QtWidgets import QSystemTrayIcon

        # Create context menu
        def close_app() -> None:
            self.close()

        menu = self.tray.create_default_menu(
            show_action=self.show_window,
            hide_action=self.hide,
            quit_action=close_app,
        )
        self.tray.set_context_menu(menu)
        self.tray.set_visible(True)

        # Handle tray activation
        def handle_tray_activation(reason: QSystemTrayIcon.ActivationReason) -> None:
            if reason in (
                QSystemTrayIcon.ActivationReason.DoubleClick,
                QSystemTrayIcon.ActivationReason.Trigger,
            ):
                self.show_window()

        self.tray.activated.connect(handle_tray_activation)

    def show_window(self) -> None:
        """Show and raise the window."""
        self.show()
        self.raise_()
        self.activateWindow()

    @Slot()
    def on_minimize_to_tray(self) -> None:
        """Minimize window to system tray."""
        if self.tray.is_available():
            self.hide()
            self.tray.show_message(
                APP_NAME,
                "Application minimized to system tray. Click the tray icon to restore.",
            )

    def _build_actions(self) -> None:
        self.action_open = QAction("Open...", self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self.on_open_file)

        self.action_work = QAction("Run background work", self)
        self.action_work.triggered.connect(self.on_run_work)

        self.action_prefs = QAction("Preferences", self)
        self.action_prefs.triggered.connect(self.on_open_prefs)

        self.action_quit = QAction("Quit", self)
        self.action_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_quit.triggered.connect(self.on_quit)

        self.action_about = QAction("About", self)
        # Set role for macOS native menu integration
        # On macOS, this makes the action appear in the app menu (e.g., "About get-gphotos-data")
        self.action_about.setMenuRole(QAction.MenuRole.AboutRole)
        self.action_about.triggered.connect(self.on_about)

        self.action_clear_recent = QAction("Clear recent files", self)
        self.action_clear_recent.triggered.connect(self.on_clear_recent)

        self.recent_menu = QMenu("Recent Files", self)

    def _create_toolbar(self) -> QToolBar:
        """Create a horizontal toolbar with square icon buttons."""
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("mainToolBar")  # Required for window state persistence

        # Set toolbar to use icon-only mode with square buttons
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        # Set icon size for square buttons (e.g., 32x32)
        icon_size = QSize(32, 32)
        toolbar.setIconSize(icon_size)

        # Create icons for actions
        self.action_open.setIcon(self._create_icon_for_action("open"))
        self.action_work.setIcon(self._create_icon_for_action("work"))
        self.action_prefs.setIcon(self._create_icon_for_action("preferences"))
        self.action_quit.setIcon(self._create_icon_for_action("quit"))

        # Add actions to toolbar
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_work)
        toolbar.addAction(self.action_prefs)
        toolbar.addSeparator()  # Visual separator before quit button
        toolbar.addAction(self.action_quit)

        return toolbar

    def _create_icon_for_action(self, action_name: str) -> QIcon:
        """Create an icon for a toolbar action.

        Creates simple colored square icons with symbols.
        Can be extended to load from image files.
        """
        # Create a colored square pixmap for the icon
        size = 32
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        # Create painter to draw the icon
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Different colors for different actions
        colors = {
            "open": QColor(52, 152, 219),  # Blue
            "work": QColor(46, 204, 113),  # Green
            "preferences": QColor(155, 89, 182),  # Purple
            "quit": QColor(231, 76, 60),  # Red
        }
        color = colors.get(action_name, QColor(149, 165, 166))  # Gray default

        # Draw filled rounded rectangle
        margin = 2
        painter.fillRect(margin, margin, size - 2 * margin, size - 2 * margin, color)

        # Add a simple symbol based on action
        painter.setPen(QColor(255, 255, 255))  # White pen
        painter.setFont(painter.font())

        if action_name == "open":
            # Draw folder icon (simplified)
            painter.drawRect(8, 10, 16, 12)
            painter.drawLine(8, 10, 12, 10)
        elif action_name == "work":
            # Draw play icon (triangle)
            center = pixmap.rect().center()
            triangle = QPolygon(
                [
                    QPoint(center.x() - 6, center.y()),
                    QPoint(center.x() + 6, center.y() - 6),
                    QPoint(center.x() + 6, center.y() + 6),
                ]
            )
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawPolygon(triangle)
        elif action_name == "preferences":
            # Draw gear icon (simplified - circles)
            center = pixmap.rect().center()
            painter.drawEllipse(center, 6, 6)
            painter.drawEllipse(center, 10, 10)
        elif action_name == "quit":
            # Draw X icon (exit/close symbol)
            center = pixmap.rect().center()
            # Draw two diagonal lines forming an X
            margin = 8
            painter.drawLine(
                center.x() - margin, center.y() - margin, center.x() + margin, center.y() + margin
            )
            painter.drawLine(
                center.x() + margin, center.y() - margin, center.x() - margin, center.y() + margin
            )

        painter.end()

        return QIcon(pixmap)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.action_open)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.action_prefs)
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)

        view_menu = self.menuBar().addMenu("&View")
        # Add toggle actions for dock widgets (will be populated after docks are created)
        self.view_menu = view_menu

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.action_about)

    def _load_ui(self) -> None:
        # Create tab widget to organize different content areas
        self.tab_widget = QTabWidget(self)

        # Tab 1: Google Photos (main feature)
        google_photos_view = GooglePhotosView(self)
        self.tab_widget.addTab(google_photos_view, "Google Photos")

        # Tab 2: Main/File operations (original UI)
        self.ui = load_ui("main_window.ui", self)
        self.tab_widget.addTab(self.ui, "Main")

        # Tab 2: Table View
        table_demo = TableViewDemo(self)
        self.tab_widget.addTab(table_demo, "Table View")

        # Tab 3: Tree View
        tree_demo = TreeViewDemo(self)
        self.tab_widget.addTab(tree_demo, "Tree View")

        # Tab 4: Controls
        controls_demo = ControlsDemo(self)
        self.tab_widget.addTab(controls_demo, "Controls")

        # Tab 5: Dialogs
        dialogs_demo = DialogsDemo(self)
        self.tab_widget.addTab(dialogs_demo, "Dialogs")

        # Tab 6: Calendar
        calendar_demo = CalendarDemo(self)
        self.tab_widget.addTab(calendar_demo, "Calendar")

        # Tab 7: Graphics View
        graphics_demo = GraphicsDemo(self)
        self.tab_widget.addTab(graphics_demo, "Graphics")

        # Tab 8: Text Editor
        text_editor_demo = TextEditorDemo(self)
        self.tab_widget.addTab(text_editor_demo, "Text Editor")

        # Set tab widget as central widget
        self.setCentralWidget(self.tab_widget)

        # Create dock widgets for additional content
        self._create_dock_widgets()

        label = self.ui.findChild(QLabel, "statusLabel")
        if label is None:
            raise RuntimeError("statusLabel not found in main_window.ui")
        self.label = label

        file_label = self.ui.findChild(QLabel, "fileLabel")
        if file_label is None:
            raise RuntimeError("fileLabel not found in main_window.ui")
        self.file_label = file_label

        file_preview = self.ui.findChild(QPlainTextEdit, "filePreview")
        if file_preview is None:
            raise RuntimeError("filePreview not found in main_window.ui")
        self.file_preview = file_preview

        progress_bar = self.ui.findChild(QProgressBar, "progressBar")
        if progress_bar is None:
            raise RuntimeError("progressBar not found in main_window.ui")
        self.progress_bar = progress_bar
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Idle")

        log_viewer = self.ui.findChild(QPlainTextEdit, "logViewer")
        if log_viewer is None:
            raise RuntimeError("logViewer not found in main_window.ui")
        self.log_viewer = log_viewer

        btn_open = self.ui.findChild(QPushButton, "openButton")
        if btn_open is None:
            raise RuntimeError("openButton not found in main_window.ui")
        self.btn_open = btn_open

        btn_work = self.ui.findChild(QPushButton, "workButton")
        if btn_work is None:
            raise RuntimeError("workButton not found in main_window.ui")
        self.btn_work = btn_work

        btn_cancel = self.ui.findChild(QPushButton, "cancelButton")
        if btn_cancel is None:
            raise RuntimeError("cancelButton not found in main_window.ui")
        self.btn_cancel = btn_cancel
        self.btn_cancel.setEnabled(False)

        btn_refresh = self.ui.findChild(QPushButton, "refreshLogButton")
        if btn_refresh is None:
            raise RuntimeError("refreshLogButton not found in main_window.ui")
        self.btn_refresh_logs = btn_refresh

        btn_prefs = self.ui.findChild(QPushButton, "prefsButton")
        if btn_prefs is None:
            raise RuntimeError("prefsButton not found in main_window.ui")
        self.btn_prefs = btn_prefs

        # Add "Minimize to tray" button programmatically
        # Find the layout and add button before prefsButton
        ui_layout = self.ui.layout()
        if ui_layout:
            btn_minimize = QPushButton("Minimize to tray", self.ui)
            self.btn_minimize_to_tray = btn_minimize

            # Find prefsButton index and insert before it
            prefs_idx = -1
            for i in range(ui_layout.count()):
                item = ui_layout.itemAt(i)
                if item and item.widget() == btn_prefs:
                    prefs_idx = i
                    break

            # Use insertWidget if it's a box layout (has the method)
            if prefs_idx >= 0 and hasattr(ui_layout, "insertWidget"):
                ui_layout.insertWidget(prefs_idx, btn_minimize)  # type: ignore[attr-defined]
            else:
                # Fallback: add at end
                ui_layout.addWidget(btn_minimize)

            # Initially hide - will be shown if tray is available
            btn_minimize.setVisible(False)

    def _create_dock_widgets(self) -> None:
        """Create dock widgets for additional content areas."""
        # Info dock widget
        info_dock = QDockWidget("Information", self)
        info_dock.setObjectName("informationDock")  # Required for window state persistence
        
        # Load UI from .ui file
        info_widget = load_ui("information_dock.ui", self)
        info_dock.setWidget(info_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, info_dock)
        # Add toggle action to View menu
        self.view_menu.addAction(info_dock.toggleViewAction())

        # Splitter demo dock (optional - can be shown via View menu)
        splitter_dock = QDockWidget("Splitter Demo", self)
        splitter_dock.setObjectName("splitterDemoDock")  # Required for window state persistence
        
        # Load UI from .ui file
        splitter_widget = load_ui("splitter_dock.ui", self)
        splitter_dock.setWidget(splitter_widget)
        # Start with info dock visible, splitter hidden
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, splitter_dock)
        splitter_dock.setVisible(False)
        # Add toggle action to View menu
        self.view_menu.addAction(splitter_dock.toggleViewAction())

    def _refresh_recent_menu(self) -> None:
        """Refresh the recent files menu with current recent files list."""
        self.recent_menu.clear()
        recent = self.file_manager.get_recent_files()
        if not recent:
            # Show disabled "No recent files" item
            empty = self.recent_menu.addAction("No recent files")
            empty.setEnabled(False)
        else:
            # Add each recent file as a menu action
            for path in recent:
                action = self.recent_menu.addAction(str(path))
                action.setData(str(path))
                action.triggered.connect(self.on_open_recent)
        self.recent_menu.addSeparator()
        self.recent_menu.addAction(self.action_clear_recent)

    def _open_files(self, paths: list[Path]) -> None:
        """Open one or more files, remembering them in recent files.

        Args:
            paths: List of file paths to open (only files, not directories, are processed)
        """
        # Filter to only actual files
        files = [path for path in paths if path.is_file()]
        if not files:
            QMessageBox.information(self, "Open file", "No files were provided.")
            return
        # Remember each file in recent files list
        for path in files:
            self.file_manager.add_recent_file(path)
        self._refresh_recent_menu()
        # Preview the first file
        self._load_file_preview(files[0])

    def _load_file_preview(self, path: Path) -> None:
        """Load and display a file preview in the preview widget.

        The preview is limited to MAX_PREVIEW_BYTES and uses UTF-8 decoding
        with error replacement to handle binary files safely.

        Args:
            path: Path to the file to preview
        """
        try:
            data = path.read_bytes()
        except OSError as exc:
            self.log.exception("Failed to read file: %s", path)
            QMessageBox.critical(self, "Open file", f"Could not read file:\n{path}\n\n{exc}")
            return

        # Limit preview size and decode safely
        preview = data[:MAX_PREVIEW_BYTES]
        text = preview.decode("utf-8", errors="replace")
        if len(data) > MAX_PREVIEW_BYTES:
            text += "\n\n[Preview truncated]"

        # Update UI
        self.file_preview.setPlainText(text)
        self.file_label.setText(f"File: {path}")
        self.label.setText(f"Opened {path.name}")
        # Remember directory for next file dialog
        self.settings.set_str(self.settings.keys.last_open_dir, str(path.parent))

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        """Handle drag enter event - accept if dragging local files.

        Args:
            event: The drag enter event
        """
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        """Handle drop event - open dropped local files.

        Args:
            event: The drop event
        """
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self._open_files(paths)
        event.acceptProposedAction()

    @Slot()
    def on_open_prefs(self) -> None:
        """Open the preferences dialog and handle theme changes."""
        dlg = PreferencesDialog(settings=self.settings, parent=self)
        dlg.theme_changed.connect(self._on_theme_changed)
        dlg.exec()

    def _on_theme_changed(self, theme: str) -> None:
        """Handle theme change from preferences dialog.

        Applies the new theme to both this window and the QApplication
        so dialogs inherit the theme.

        Args:
            theme: Theme name (e.g., "light" or "dark")
        """
        from .core.paths import qss_text

        try:
            qss = qss_text(theme)
            # Apply to this window
            self.setStyleSheet(qss)
            # Also update the QApplication so dialogs inherit the theme
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app and isinstance(app, QApplication):
                app.setStyleSheet(qss)
            self.statusBar().showMessage(f"Theme changed to {theme}", 2000)
        except FileNotFoundError:
            self.log.warning("QSS stylesheet not found for theme: %s", theme)
            QMessageBox.warning(self, "Theme", f"Stylesheet not found for theme: {theme}")

    @Slot()
    def on_open_file(self) -> None:
        """Open file dialog to select and open a file.

        Uses the last opened directory as the starting location, or
        the user's home directory if no previous directory is saved.
        """
        start_dir = self.settings.get_str(self.settings.keys.last_open_dir, "")
        if not start_dir:
            start_dir = str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open file",
            start_dir,
            "All files (*);;Text files (*.txt *.md *.py)",
        )
        if not file_path:
            return
        self._open_files([Path(file_path)])

    @Slot()
    def on_open_recent(self) -> None:
        """Open a file from the recent files menu.

        Triggered when user clicks a file in the recent files menu.
        The file path is stored in the QAction's data.
        """
        action = self.sender()
        if not isinstance(action, QAction):
            return
        data = action.data()
        if not data:
            return
        self._open_files([Path(str(data))])

    @Slot()
    def on_clear_recent(self) -> None:
        """Clear all recent files from the list and refresh the menu."""
        self.file_manager.clear_recent_files()
        self._refresh_recent_menu()

    @Slot()
    def on_about(self) -> None:
        from .core.paths import app_version
        from .dialogs.about import AboutDialog

        dlg = AboutDialog(version=app_version(), release_notes_url="", parent=self)
        dlg.exec()

    def _set_working_state(self, working: bool) -> None:
        """Update UI state to reflect whether background work is running.

        Args:
            working: True if work is in progress, False otherwise
        """
        self.btn_work.setEnabled(not working)
        self.action_work.setEnabled(not working)
        self.btn_cancel.setEnabled(working)

    @Slot()
    def on_run_work(self) -> None:
        """Start a background work task with progress tracking.

        Demonstrates the worker system with a simple task that:
        - Runs in a background thread
        - Reports progress updates
        - Supports cancellation
        - Updates UI safely via signals/callbacks
        """
        if self.active_worker is not None:
            QMessageBox.information(self, "Background work", "Work is already running.")
            return

        # Initialize UI for work
        self.label.setText("Working in background...")
        self.statusBar().showMessage("Working in background...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Working... %p%")
        self._set_working_state(True)

        def work(ctx: WorkContext) -> str:
            """Background work function - runs in worker thread.

            This function demonstrates:
            - Checking for cancellation
            - Reporting progress
            - Returning a result
            """
            steps = 10
            for step in range(steps):
                ctx.check_cancelled()  # Cooperative cancellation check
                time.sleep(0.25)  # Simulate work
                percent = int(((step + 1) / steps) * 100)
                ctx.progress(percent, f"Step {step + 1} of {steps}")
            return "Done."

        def progress(percent: int, message: str) -> None:
            """Progress callback - runs on main thread via signal."""
            self.progress_bar.setValue(percent)
            if message:
                self.label.setText(message)
                self.statusBar().showMessage(message, 2000)

        def done(result: str) -> None:
            """Completion callback - runs on main thread when worker finishes."""
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Done")
            self.label.setText(result)
            self.statusBar().showMessage("Background work finished", 3000)
            self._set_working_state(False)
            self.active_worker = None
            self.log.info("Background work finished")

        def cancelled() -> None:
            """Cancellation callback - runs on main thread when work is cancelled."""
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Cancelled")
            self.label.setText("Cancelled")
            self.statusBar().showMessage("Background work cancelled", 3000)
            self._set_working_state(False)
            self.active_worker = None
            self.log.info("Background work cancelled")

        def error(msg: str) -> None:
            """Error callback - runs on main thread when work fails."""
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Error")
            self.label.setText("Error")
            self.statusBar().showMessage("Background work failed", 3000)
            self._set_working_state(False)
            self.active_worker = None
            QMessageBox.critical(self, "Worker error", msg)

        req = WorkRequest(
            fn=work,
            on_done=done,
            on_error=error,
            on_progress=progress,
            on_cancel=cancelled,
        )
        self.active_worker = self.pool.submit(req)

    @Slot()
    def on_cancel_work(self) -> None:
        """Cancel the currently running background work task.

        Sends a cancellation request to the worker and updates the UI.
        The worker will check for cancellation at the next check_cancelled()
        call and exit cooperatively.
        """
        if self.active_worker is None:
            return
        self.active_worker.cancel()
        self.label.setText("Cancel requested...")
        self.statusBar().showMessage("Cancel requested...", 3000)
        self.btn_cancel.setEnabled(False)

    @Slot()
    def on_quit(self) -> None:
        """Handle quit action with proper cleanup.

        Checks for running background workers and handles them appropriately.
        If a worker is running, asks the user if they want to cancel it and exit.
        """
        # Check if there's an active worker
        if self.active_worker is not None:
            reply = QMessageBox.question(
                self,
                "Exit Application",
                "A background task is currently running.\n\n"
                "Do you want to cancel the task and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.No:
                # User cancelled the quit dialog
                return
            # User chose Yes - cancel the worker and exit
            self.active_worker.cancel()
            self.label.setText("Cancelling task before exit...")
            self.statusBar().showMessage("Cancelling task before exit...", 2000)
            # Give the worker a brief moment to cancel cooperatively
            # The closeEvent will also handle cleanup if the worker is still running
            def delayed_close() -> None:
                """Close after a brief delay to allow cancellation."""
                self.close()

            QTimer.singleShot(500, delayed_close)  # Wait 500ms
            return

        # No active worker - exit immediately
        self.close()

    @Slot()
    def on_refresh_logs(self) -> None:
        """Refresh the log viewer with current log file contents.

        Reads the rotating log file and displays the last LOG_PREVIEW_BYTES
        bytes. If the file is larger, shows a truncation notice.
        """
        log_path = app_data_dir() / "app.log"
        if not log_path.exists():
            self.log_viewer.setPlainText(f"Log file not found: {log_path}")
            return

        try:
            data = log_path.read_bytes()
        except OSError as exc:
            self.log_viewer.setPlainText(f"Could not read log file:\n{log_path}\n\n{exc}")
            return

        # Show last N bytes if file is large
        if len(data) > LOG_PREVIEW_BYTES:
            data = data[-LOG_PREVIEW_BYTES:]
            header = f"[Showing last {LOG_PREVIEW_BYTES} bytes]\n\n"
        else:
            header = ""

        # Decode with error replacement to handle non-UTF-8 content safely
        text = header + data.decode("utf-8", errors="replace")
        self.log_viewer.setPlainText(text)
        # Scroll to end to show most recent logs
        self.log_viewer.moveCursor(QTextCursor.MoveOperation.End)
        self.statusBar().showMessage("Logs refreshed", 2000)

    def _setup_command_palette(self) -> None:
        """Initialize command palette with commands and keyboard shortcut."""
        commands = [
            Command(
                name="Open File",
                description="Open a file from disk",
                shortcut="Ctrl+O",
                action=self.on_open_file,
            ),
            Command(
                name="Run Background Work",
                description="Execute background task",
                shortcut="",
                action=self.on_run_work,
            ),
            Command(
                name="Preferences",
                description="Open preferences dialog",
                shortcut="Ctrl+,",
                action=self.on_open_prefs,
            ),
            Command(
                name="Refresh Logs",
                description="Refresh the log viewer",
                shortcut="",
                action=self.on_refresh_logs,
            ),
            Command(
                name="About",
                description="Show about dialog",
                shortcut="",
                action=self.on_about,
            ),
            Command(
                name="Quit",
                description="Exit the application",
                shortcut="Ctrl+Q",
                action=lambda: [self.close(), None][1],  # type: ignore[return-value]
            ),
        ]

        # Create command palette shortcut (Ctrl+K or Ctrl+P)
        cmd_palette_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        cmd_palette_shortcut.activated.connect(lambda: self._show_command_palette(commands))

        # Alternative shortcut (Ctrl+Shift+P like VS Code)
        cmd_palette_shortcut2 = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        cmd_palette_shortcut2.activated.connect(lambda: self._show_command_palette(commands))

    def _show_command_palette(self, commands: list[Command]) -> None:
        """Show the command palette dialog and execute selected command.

        Args:
            commands: List of Command objects to display in the palette
        """
        palette = CommandPalette(commands, self)
        # Position dialog centered horizontally near top of window
        palette.move(
            self.geometry().center().x() - palette.width() // 2,
            self.geometry().top() + 50,
        )
        # Execute command if one was selected
        if (
            palette.exec() == palette.DialogCode.Accepted
            and palette.selected_command
            and palette.selected_command.action
        ):
            palette.selected_command.action()

    def changeEvent(self, event) -> None:  # type: ignore[override]
        """Handle window state changes (minimize to tray)."""
        from PySide6.QtCore import QEvent

        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and self.tray.is_available()
        ):
            # Optionally hide window when minimized if tray is available
            # Uncomment to enable minimize-to-tray:
            # self.hide()
            # self.tray.show_message("Minimized", "Application minimized to system tray")
            pass

        super().changeEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Save window state before closing and cleanup resources."""
        # Cancel any active worker if still running
        if self.active_worker is not None:
            self.active_worker.cancel()
            self.active_worker = None

        # Save window state
        self.window_state.save_state()

        # Cleanup system tray
        if self.tray.is_available():
            self.tray.set_visible(False)

        super().closeEvent(event)
