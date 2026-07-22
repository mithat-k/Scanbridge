"""
ui/main_window.py

Main application window for Scanbridge.

Responsibilities:
- Build and display the primary UI (header, content, footer).
- Run a background health check on startup (GPU / CPU detection).
- Manage the PDF-to-HTML OCR conversion lifecycle.
- Support live language switching via the Translator's language_changed signal.
- Comply with WCAG 2.1 accessibility requirements (keyboard focus, screen reader events).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.ocr_worker import OCRWorker

from PyQt6.QtCore import Qt, QTimer, QCoreApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QFileDialog,
    QSizePolicy, QFrame, QSpacerItem,
)

# QAccessible may not be available in all PyQt6 builds (e.g. Python 3.14).
# Use it when present, otherwise fall back to setAccessibleName only.
try:
    from PyQt6.QtGui import QAccessible, QAccessibleEvent
    _HAS_QACCESSIBLE = True
except ImportError:
    _HAS_QACCESSIBLE = False

from engine.health_checker import HealthCheckerWorker
from utils.i18n import translator


# ---------------------------------------------------------------------------
# Screen reader helper — QAccessible (if available) or setAccessibleName fallback
# ---------------------------------------------------------------------------

def _announce(widget: QLabel, message: str, *, event_type=None) -> None:
    """
    Update a label's text and announce it to screen readers.

    Uses QAccessibleEvent when QAccessible is available; otherwise
    falls back to setAccessibleName so the text is still exposed via AT-SPI.

    Important: we intentionally do NOT gate on QAccessible.isActive().
    During startup, NVDA/JAWS may not have activated Qt's accessibility
    subsystem yet, so isActive() returns False and the Alert event would
    never be emitted. Qt handles updateAccessibility() safely even when
    no AT is active — it is a no-op in that case, not an error.
    """
    widget.setText(message)
    widget.setAccessibleName(message)
    widget.setToolTip(message)

    if _HAS_QACCESSIBLE:
        try:
            if event_type is None:
                event_type = QAccessible.Event.NameChanged
            event = QAccessibleEvent(widget, event_type)
            QAccessible.updateAccessibility(event)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QWidget):
    """
    Responsive, accessible Scanbridge main window.

    On startup a HealthCheckerWorker runs in the background; its result
    is announced to screen readers and used to configure the OCR engine.
    All visible strings are retrieved from the Translator so the UI
    reacts to language changes without restarting.
    """

    # Color palette — defined once for easy maintenance
    _CLR_BG          = "#0F0F0F"
    _CLR_SURFACE     = "#1A1A2E"
    _CLR_ACCENT      = "#4F8EF7"
    _CLR_ACCENT_HOV  = "#3A72D4"
    _CLR_ACCENT_PRE  = "#2A5BB0"
    _CLR_SUCCESS     = "#4CAF50"
    _CLR_WARNING     = "#FFC107"
    _CLR_DISABLED_BG = "#2A2A2A"
    _CLR_DISABLED_FG = "#666666"
    _CLR_TEXT        = "#E8E8F0"
    _CLR_SUBTEXT     = "#A0A0B0"
    _CLR_BORDER      = "#2E2E4E"

    def __init__(self, engine_worker_class) -> None:
        super().__init__()
        self.engine_worker_class = engine_worker_class
        self.ocr_worker: OCRWorker | None = None
        self.gpu_enabled: bool = False
        self.device_type: str = "cpu"
        self._converting: bool = False  # Guard against double-conversion
        self._first_show: bool = True   # Tracks the very first showEvent call

        self._build_ui()
        self._run_health_check()

        # Connect to live language switching
        translator.language_changed.connect(self._retranslate_ui)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(translator.t("app.title"))
        self.setMinimumSize(460, 320)
        self.resize(620, 420)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._apply_stylesheet()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header strip ─────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("header")
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(28, 22, 28, 18)
        h_layout.setSpacing(4)

        # Top row: title + settings button
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self._title_label = QLabel(translator.t("app.name"))
        self._title_label.setObjectName("appTitle")
        title_row.addWidget(self._title_label, stretch=1)

        self._settings_btn = QPushButton(translator.t("buttons.settings"))
        self._settings_btn.setObjectName("settingsBtn")
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._settings_btn.clicked.connect(self._open_settings)
        title_row.addWidget(self._settings_btn)

        h_layout.addLayout(title_row)

        self._subtitle_label = QLabel(translator.t("app.subtitle"))
        self._subtitle_label.setObjectName("appSubtitle")
        h_layout.addWidget(self._subtitle_label)

        root.addWidget(header)

        # ── Content area ─────────────────────────────────────────────
        content = QFrame()
        content.setObjectName("content")
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(28, 24, 28, 24)
        c_layout.setSpacing(16)

        # System status label (acts as an ARIA live region)
        self.status_label = QLabel(translator.t("status.starting"))
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.status_label.setAccessibleName(translator.t("status.starting"))
        c_layout.addWidget(self.status_label)

        # Hardware badge (GPU / CPU indicator)
        self.hw_badge = QLabel("")
        self.hw_badge.setObjectName("hwBadge")
        self.hw_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hw_badge.setWordWrap(True)
        self.hw_badge.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.hw_badge.setVisible(False)
        c_layout.addWidget(self.hw_badge)

        c_layout.addItem(QSpacerItem(0, 8))

        # Primary action button — disabled until health check finishes
        self.select_btn = QPushButton(translator.t("buttons.select_and_convert"))
        self.select_btn.setObjectName("primaryBtn")
        self.select_btn.setAccessibleName(translator.t("buttons.select_and_convert"))
        self.select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.select_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.select_btn.setEnabled(False)
        self.select_btn.clicked.connect(self._on_select_clicked)
        c_layout.addWidget(self.select_btn)

        # Cancel button — visible only during conversion
        self.cancel_btn = QPushButton(translator.t("buttons.cancel"))
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setAccessibleName(translator.t("buttons.cancel"))
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.cancel_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        c_layout.addWidget(self.cancel_btn)

        # Conversion progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.progress_bar.setAccessibleName(translator.t("progress.bar_label"))
        c_layout.addWidget(self.progress_bar)

        root.addWidget(content, stretch=1)

        # ── Footer ───────────────────────────────────────────────────
        self._footer_label = QLabel(translator.t("app.footer"))
        self._footer_label.setObjectName("footer")
        self._footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        root.addWidget(self._footer_label)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(f"""
            /* General */
            QWidget {{
                background-color: {self._CLR_BG};
                color: {self._CLR_TEXT};
                font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
            }}

            /* Header strip */
            QFrame#header {{
                background-color: {self._CLR_SURFACE};
                border-bottom: 1px solid {self._CLR_BORDER};
            }}
            QLabel#appTitle {{
                font-size: 20pt;
                font-weight: 700;
                color: {self._CLR_ACCENT};
                padding: 0;
            }}
            QLabel#appSubtitle {{
                font-size: 10pt;
                color: {self._CLR_SUBTEXT};
                padding: 0;
            }}

            /* Settings button */
            QPushButton#settingsBtn {{
                background-color: transparent;
                color: {self._CLR_SUBTEXT};
                border: 1px solid {self._CLR_BORDER};
                font-size: 10pt;
                padding: 4px 12px;
                border-radius: 6px;
            }}
            QPushButton#settingsBtn:hover   {{ color: {self._CLR_TEXT}; border-color: {self._CLR_ACCENT}; }}
            QPushButton#settingsBtn:pressed {{ background-color: rgba(79,142,247,0.10); }}
            QPushButton#settingsBtn:focus   {{
                outline: none;
                border: 2px dashed #FFD700;
            }}

            /* Content area */
            QFrame#content {{
                background-color: {self._CLR_BG};
            }}

            /* Status label */
            QLabel#statusLabel {{
                font-size: 12pt;
                color: {self._CLR_TEXT};
                line-height: 1.5;
                padding: 4px 0;
            }}

            /* Hardware badge */
            QLabel#hwBadge {{
                font-size: 10pt;
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 6px;
            }}
            QLabel#hwBadge[gpu="true"] {{
                color: {self._CLR_SUCCESS};
                background-color: rgba(76, 175, 80, 0.12);
                border: 1px solid rgba(76, 175, 80, 0.35);
            }}
            QLabel#hwBadge[gpu="false"] {{
                color: {self._CLR_WARNING};
                background-color: rgba(255, 193, 7, 0.10);
                border: 1px solid rgba(255, 193, 7, 0.30);
            }}

            /* Primary action button */
            QPushButton#primaryBtn {{
                background-color: {self._CLR_ACCENT};
                border: none;
                color: #FFFFFF;
                font-size: 13pt;
                font-weight: 600;
                padding: 14px 24px;
                border-radius: 10px;
                min-height: 48px;
            }}
            QPushButton#primaryBtn:hover   {{ background-color: {self._CLR_ACCENT_HOV}; }}
            QPushButton#primaryBtn:pressed {{ background-color: {self._CLR_ACCENT_PRE}; }}
            QPushButton#primaryBtn:focus   {{
                outline: none;
                border: 2px dashed #FFD700;
                background-color: {self._CLR_ACCENT_HOV};
            }}
            QPushButton#primaryBtn:disabled {{
                background-color: {self._CLR_DISABLED_BG};
                color: {self._CLR_DISABLED_FG};
            }}

            /* Cancel button */
            QPushButton#cancelBtn {{
                background-color: transparent;
                border: 1px solid {self._CLR_WARNING};
                color: {self._CLR_WARNING};
                font-size: 11pt;
                font-weight: 600;
                padding: 10px 24px;
                border-radius: 10px;
                min-height: 40px;
            }}
            QPushButton#cancelBtn:hover   {{ background-color: rgba(255, 193, 7, 0.10); }}
            QPushButton#cancelBtn:pressed {{ background-color: rgba(255, 193, 7, 0.20); }}
            QPushButton#cancelBtn:focus   {{
                outline: none;
                border: 2px dashed #FFD700;
            }}

            /* Progress bar */
            QProgressBar#progressBar {{
                border: 1px solid {self._CLR_BORDER};
                border-radius: 6px;
                background-color: {self._CLR_SURFACE};
                text-align: center;
                font-size: 9pt;
                min-height: 24px;
                color: {self._CLR_TEXT};
            }}
            QProgressBar#progressBar::chunk {{
                background-color: {self._CLR_ACCENT};
                border-radius: 5px;
            }}

            /* Footer */
            QLabel#footer {{
                font-size: 8pt;
                color: {self._CLR_SUBTEXT};
                padding: 8px 0;
                border-top: 1px solid {self._CLR_BORDER};
                background-color: {self._CLR_SURFACE};
            }}
        """)

    # ------------------------------------------------------------------
    # Window show event — initial focus management
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        """
        Called once by Qt when the window becomes visible.

        On the very first show we defer focus assignment by one event-loop
        tick (QTimer.singleShot with 0 ms) so that:
          1. The window is fully painted and has received its WM_ACTIVATE
             message from Windows before we move focus.
          2. NVDA / JAWS / Narrator have had a chance to enumerate the new
             top-level window via WinEvent hooks before focus lands inside it.

        Focus target priority:
          • settings_btn  — always interactive, so it is a safe first-focus
            target while the health check is still running and select_btn
            is disabled.
          • If the health check has already finished and select_btn is
            enabled we prefer it because it is the primary action.

        We only do this on the *first* show; subsequent show() calls (e.g.
        after minimise/restore) must not steal focus unexpectedly (WCAG 3.2.1).
        """
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            # 150ms delay gives Windows and the screen reader enough time
            # to build the accessibility tree before we move focus.
            QTimer.singleShot(150, self._set_initial_focus)

    def _set_initial_focus(self) -> None:
        """
        Move keyboard focus to the most appropriate widget after startup.

        Called from showEvent via QTimer.singleShot so Qt's event loop has
        completed one full cycle and the OS window is active.
        """
        target = self.select_btn if self.select_btn.isEnabled() else self._settings_btn
        target.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------
    # Live translation update
    # ------------------------------------------------------------------

    def _retranslate_ui(self, _lang: str = "") -> None:
        """
        Called by the Translator's language_changed signal.
        Re-applies all translatable strings to the UI widgets in place
        — no window rebuild or application restart required.
        """
        self.setWindowTitle(translator.t("app.title"))
        self._title_label.setText(translator.t("app.name"))
        self._subtitle_label.setText(translator.t("app.subtitle"))
        self._footer_label.setText(translator.t("app.footer"))
        self._settings_btn.setText(translator.t("buttons.settings"))

        self.select_btn.setText(translator.t("buttons.select_and_convert"))
        self.select_btn.setAccessibleName(translator.t("buttons.select_and_convert"))

        self.cancel_btn.setText(translator.t("buttons.cancel"))
        self.cancel_btn.setAccessibleName(translator.t("buttons.cancel"))

        self.progress_bar.setAccessibleName(translator.t("progress.bar_label"))

        # Only update the status label if it isn't mid-conversion
        # (to avoid clobbering a live progress message)
        if not self._converting:
            current_status = self.status_label.text()
            # Refresh to the generic "starting" placeholder only when idle
            if current_status in (
                translator.t("status.starting"),
                translator.t("status.scanning_system"),
            ):
                self.status_label.setText(translator.t("status.starting"))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        """Open the Settings dialog."""
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def _run_health_check(self) -> None:
        """Start the HealthCheckerWorker and connect its signals."""
        self._health_worker = HealthCheckerWorker()
        self._health_worker.loading.connect(self._on_health_loading)
        self._health_worker.result_ready.connect(self._on_health_done)
        self._health_worker.start()

    def _on_health_loading(self, message: str) -> None:
        """Display the loading message and announce it to screen readers."""
        if _HAS_QACCESSIBLE:
            _announce(self.status_label, message, event_type=QAccessible.Event.Alert)
        else:
            _announce(self.status_label, message)

    def _on_health_done(self, health: dict) -> None:
        """Update the UI after the hardware check completes."""
        self.gpu_enabled = health["gpu_available"]
        self.device_type = health["device_type"]

        announcement = health["announcement"]
        if _HAS_QACCESSIBLE:
            _announce(self.status_label, announcement, event_type=QAccessible.Event.Alert)
        else:
            _announce(self.status_label, announcement)

        # Hardware badge
        badge_text = health["recommendation"]
        self.hw_badge.setText(badge_text)
        self.hw_badge.setAccessibleName(badge_text)
        self.hw_badge.setProperty("gpu", "true" if self.gpu_enabled else "false")
        self.hw_badge.style().unpolish(self.hw_badge)
        self.hw_badge.style().polish(self.hw_badge)
        self.hw_badge.setVisible(True)

        # Enable primary action and move focus to it so the screen reader
        # announces that the app is ready to use.
        self.select_btn.setEnabled(True)
        self.select_btn.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------
    # Conversion flow
    # ------------------------------------------------------------------

    def _on_select_clicked(self) -> None:
        """Open file dialog and start conversion if a file is selected."""
        if self._converting:
            return  # Guard against double-conversion
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            translator.t("file_dialog.title"),
            "",
            translator.t("file_dialog.filter"),
        )
        if file_path:
            self._start_conversion(file_path)

    def _start_conversion(self, file_path: str) -> None:
        self._converting = True
        self.select_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        file_name = os.path.basename(file_path)
        msg = translator.t("status.processing", filename=file_name)
        if _HAS_QACCESSIBLE:
            _announce(self.status_label, msg, event_type=QAccessible.Event.Alert)
        else:
            _announce(self.status_label, msg)

        # Disconnect and stop any previous worker
        if self.ocr_worker is not None:
            try:
                self.ocr_worker.progress.disconnect()
                self.ocr_worker.result_ready.disconnect()
                self.ocr_worker.error.disconnect()
            except RuntimeError:
                pass  # Already disconnected — safe to ignore
            if self.ocr_worker.isRunning():
                self.ocr_worker.cancel()
                self.ocr_worker.wait(2000)

        self.ocr_worker = self.engine_worker_class(
            file_path,
            gpu_enabled=self.gpu_enabled,
            device_type=self.device_type,
        )
        self.ocr_worker.progress.connect(self._on_progress)
        self.ocr_worker.result_ready.connect(self._on_finished)
        self.ocr_worker.error.connect(self._on_error)
        self.ocr_worker.start()

    def _on_progress(self, value: int, message: str) -> None:
        self.progress_bar.setValue(value)
        if message:
            self.status_label.setText(message)
            self.status_label.setAccessibleName(message)

    def _on_cancel_clicked(self) -> None:
        """Cancel the active OCR worker and reset the UI."""
        if self.ocr_worker is not None and self.ocr_worker.isRunning():
            self.ocr_worker.cancel()
        self._reset_ui_after_conversion()
        msg = translator.t("status.cancelled")
        if _HAS_QACCESSIBLE:
            _announce(self.status_label, msg, event_type=QAccessible.Event.Alert)
        else:
            _announce(self.status_label, msg)

    def _reset_ui_after_conversion(self) -> None:
        """Restore the UI to its idle state after conversion ends or is cancelled."""
        self._converting = False
        self.select_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

    def _on_finished(self, output_path: str) -> None:
        self._reset_ui_after_conversion()
        self.progress_bar.setValue(100)
        msg = translator.t("status.conversion_complete")
        if _HAS_QACCESSIBLE:
            _announce(self.status_label, msg, event_type=QAccessible.Event.Alert)
        else:
            _announce(self.status_label, msg)

    def _on_error(self, error_message: str) -> None:
        # The cancel sentinel comes from the worker's own cancel() call;
        # _on_cancel_clicked already handled the UI update.
        if error_message == translator.t("status.cancel_sentinel"):
            return
        self._reset_ui_after_conversion()
        self.progress_bar.setValue(0)
        msg = translator.t("status.error", message=error_message)
        if _HAS_QACCESSIBLE:
            _announce(self.status_label, msg, event_type=QAccessible.Event.Alert)
        else:
            _announce(self.status_label, msg)

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """Gracefully stop all background threads before closing."""
        # OCR worker
        if self.ocr_worker is not None and self.ocr_worker.isRunning():
            try:
                self.ocr_worker.progress.disconnect()
                self.ocr_worker.result_ready.disconnect()
                self.ocr_worker.error.disconnect()
            except RuntimeError:
                pass
            self.ocr_worker.cancel()
            self.ocr_worker.wait(3000)

        # Health checker worker
        if hasattr(self, "_health_worker") and self._health_worker.isRunning():
            try:
                self._health_worker.loading.disconnect()
                self._health_worker.result_ready.disconnect()
            except RuntimeError:
                pass
            self._health_worker.quit()
            self._health_worker.wait(2000)

        event.accept()
