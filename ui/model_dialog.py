"""
ui/model_dialog.py

Model preparation dialog — shown while OCR models are loaded or downloaded
on first use (or after a device / language change).

- Indeterminate (busy) bar while a model is loading from disk.
- Determinate bar with MB counters while weights are being downloaded.
- Cancel button / Esc / window close request cancellation of the conversion.
- Screen-reader friendly: stage changes are announced, download progress is
  announced in 10 % steps only so speech is not flooded.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
)

try:
    from PyQt6.QtGui import QAccessible, QAccessibleEvent
    _HAS_QACCESSIBLE = True
except ImportError:
    _HAS_QACCESSIBLE = False

from utils.i18n import translator

_BAR_MAX = 1000  # determinate bar resolution (0.1 %)


def _fmt_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f}"


class ModelPrepDialog(QDialog):
    """Window-modal progress dialog for model loading / downloading."""

    cancel_requested = pyqtSignal()

    _CLR_BG      = "#0F0F0F"
    _CLR_SURFACE = "#1A1A2E"
    _CLR_ACCENT  = "#4F8EF7"
    _CLR_TEXT    = "#E8E8F0"
    _CLR_SUBTEXT = "#A0A0B0"
    _CLR_BORDER  = "#2E2E4E"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(420)
        # No "?" help button; keep the close button (it maps to cancel).
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self._closing = False          # True while finish() closes the dialog
        self._last_announced_step = -1  # last announced 10 % step
        self._stage_text = ""
        self._has_download = False

        self._build_ui()
        self._apply_stylesheet()
        self.retranslate()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)

        self._heading = QLabel()
        self._heading.setObjectName("dlgHeading")
        self._heading.setWordWrap(True)
        root.addWidget(self._heading)

        self._stage_label = QLabel()
        self._stage_label.setObjectName("dlgStage")
        self._stage_label.setWordWrap(True)
        root.addWidget(self._stage_label)

        self._bar = QProgressBar()
        self._bar.setObjectName("dlgBar")
        self._bar.setRange(0, 0)  # busy until a download reports a size
        self._bar.setTextVisible(False)
        root.addWidget(self._bar)

        self._detail_label = QLabel()
        self._detail_label.setObjectName("dlgDetail")
        self._detail_label.setWordWrap(True)
        root.addWidget(self._detail_label)

        self._hint_label = QLabel()
        self._hint_label.setObjectName("dlgHint")
        self._hint_label.setWordWrap(True)
        root.addWidget(self._hint_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._cancel_btn = QPushButton()
        self._cancel_btn.setObjectName("dlgCancelBtn")
        self._cancel_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)
        root.addLayout(btn_row)

        self._cancel_btn.setDefault(True)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {self._CLR_BG};
                color: {self._CLR_TEXT};
                font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
            }}
            QLabel#dlgHeading {{ font-size: 13pt; font-weight: 600; color: {self._CLR_TEXT}; }}
            QLabel#dlgStage   {{ font-size: 11pt; color: {self._CLR_TEXT}; }}
            QLabel#dlgDetail  {{ font-size: 10pt; color: {self._CLR_SUBTEXT}; }}
            QLabel#dlgHint    {{ font-size: 9pt;  color: {self._CLR_SUBTEXT}; }}
            QProgressBar#dlgBar {{
                background-color: {self._CLR_SURFACE};
                border: 1px solid {self._CLR_BORDER};
                border-radius: 6px;
                min-height: 14px;
                max-height: 14px;
            }}
            QProgressBar#dlgBar::chunk {{
                background-color: {self._CLR_ACCENT};
                border-radius: 5px;
            }}
            QPushButton#dlgCancelBtn {{
                background-color: {self._CLR_SURFACE};
                color: {self._CLR_TEXT};
                border: 1px solid {self._CLR_BORDER};
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 10pt;
            }}
            QPushButton#dlgCancelBtn:hover {{ border-color: {self._CLR_ACCENT}; }}
            QPushButton#dlgCancelBtn:focus {{ border: 2px solid {self._CLR_ACCENT}; }}
        """)

    def retranslate(self) -> None:
        title = translator.t("model_dialog.title")
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        self._heading.setText(translator.t("model_dialog.heading"))
        self._hint_label.setText(translator.t("model_dialog.hint"))
        self._cancel_btn.setText(translator.t("buttons.cancel"))
        self._cancel_btn.setAccessibleName(translator.t("buttons.cancel"))
        self._bar.setAccessibleName(translator.t("model_dialog.bar_label"))

    # ------------------------------------------------------------------
    # Accessibility
    # ------------------------------------------------------------------

    def _announce(self, label: QLabel, text: str, alert: bool = False) -> None:
        label.setText(text)
        label.setAccessibleName(text)
        if not _HAS_QACCESSIBLE:
            return
        try:
            event_type = QAccessible.Event.Alert if alert else QAccessible.Event.NameChanged
            QAccessible.updateAccessibility(QAccessibleEvent(label, event_type))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API (called from MainWindow slots)
    # ------------------------------------------------------------------

    def set_stage(self, message: str) -> None:
        """A new model started loading: busy bar, clear download details."""
        self._stage_text = message
        self._has_download = False
        self._last_announced_step = -1
        self._bar.setRange(0, 0)
        self._detail_label.clear()
        self._cancel_btn.setEnabled(True)
        self._announce(self._stage_label, message, alert=True)

    def set_download(self, label: str, done: int, total: int) -> None:
        """Update the bar from a download progress report (bytes)."""
        name = label or translator.t("model_dialog.unnamed_file")

        if not self._has_download:
            self._has_download = True
            self._announce(
                self._stage_label,
                translator.t("model_dialog.downloading", stage=self._stage_text),
                alert=True,
            )

        if total > 0:
            pct = min(100, int(done * 100 / total))
            self._bar.setRange(0, _BAR_MAX)
            self._bar.setValue(min(_BAR_MAX, int(done * _BAR_MAX / total)))
            text = translator.t(
                "model_dialog.download_known",
                file=name, done=_fmt_mb(done), total=_fmt_mb(total), percent=pct,
            )
            step = pct // 10
            if step != self._last_announced_step:
                self._last_announced_step = step
                self._announce(self._detail_label, text)
            else:
                self._detail_label.setText(text)
                self._detail_label.setAccessibleName(text)
        else:
            self._bar.setRange(0, 0)
            text = translator.t("model_dialog.download_unknown", file=name, done=_fmt_mb(done))
            self._detail_label.setText(text)
            self._detail_label.setAccessibleName(text)

    def finish(self) -> None:
        """Close without requesting cancellation."""
        self._closing = True
        try:
            self.accept()
        finally:
            self._closing = False

    # ------------------------------------------------------------------
    # Cancel handling — Cancel button, Esc and the title-bar close all
    # end up in reject().
    # ------------------------------------------------------------------

    def reject(self) -> None:
        if not self._closing:
            self._cancel_btn.setEnabled(False)
            self._announce(self._stage_label, translator.t("model_dialog.cancelling"), alert=True)
            self.cancel_requested.emit()
        super().reject()
