"""
ui/settings_dialog.py

Settings dialog that allows the user to change the interface language.
Changes are applied live via the Translator's language_changed signal
without requiring an application restart.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFrame,
)

from utils.i18n import translator


class SettingsDialog(QDialog):
    """
    Modal settings dialog with a language selector.

    When the user saves their choice, the Translator switches the active
    language and emits language_changed so the main window refreshes
    immediately.
    """

    # Color palette — aligned with MainWindow for visual consistency
    _CLR_BG      = "#0F0F0F"
    _CLR_SURFACE = "#1A1A2E"
    _CLR_ACCENT  = "#4F8EF7"
    _CLR_TEXT    = "#E8E8F0"
    _CLR_SUBTEXT = "#A0A0B0"
    _CLR_BORDER  = "#2E2E4E"
    _CLR_WARNING = "#FFC107"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(360)
        self._build_ui()
        self._apply_stylesheet()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(translator.t("settings_dialog.title"))

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(20)

        # Language row
        lang_row = QHBoxLayout()
        lang_row.setSpacing(16)

        self._lang_label = QLabel(translator.t("settings_dialog.language_label"))
        self._lang_label.setObjectName("settingsLabel")

        self._lang_combo = QComboBox()
        self._lang_combo.setObjectName("langCombo")
        self._lang_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._lang_combo.addItem(translator.t("settings_dialog.language_tr"), "tr")
        self._lang_combo.addItem(translator.t("settings_dialog.language_en"), "en")

        # Pre-select the currently active language
        current = translator.current_language
        index = self._lang_combo.findData(current)
        if index >= 0:
            self._lang_combo.setCurrentIndex(index)

        lang_row.addWidget(self._lang_label)
        lang_row.addWidget(self._lang_combo, stretch=1)
        root.addLayout(lang_row)

        # Notice label
        self._notice_label = QLabel("")
        self._notice_label.setObjectName("noticeLabel")
        self._notice_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notice_label.setWordWrap(True)
        self._notice_label.setVisible(False)
        root.addWidget(self._notice_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        root.addWidget(sep)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._cancel_btn = QPushButton(translator.t("settings_dialog.cancel_button"))
        self._cancel_btn.setObjectName("dlgCancelBtn")
        self._cancel_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._cancel_btn.clicked.connect(self.reject)

        self._save_btn = QPushButton(translator.t("settings_dialog.save_button"))
        self._save_btn.setObjectName("dlgSaveBtn")
        self._save_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._save_btn.clicked.connect(self._on_save)

        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._save_btn)
        root.addLayout(btn_row)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {self._CLR_BG};
                color: {self._CLR_TEXT};
                font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
            }}
            QLabel#settingsLabel {{
                font-size: 11pt;
                color: {self._CLR_TEXT};
            }}
            QLabel#noticeLabel {{
                font-size: 9pt;
                color: {self._CLR_ACCENT};
                padding: 4px 0;
            }}
            QFrame#separator {{
                border: none;
                border-top: 1px solid {self._CLR_BORDER};
            }}
            QComboBox#langCombo {{
                background-color: {self._CLR_SURFACE};
                color: {self._CLR_TEXT};
                border: 1px solid {self._CLR_BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 10pt;
                min-height: 32px;
            }}
            QComboBox#langCombo::drop-down {{
                border: none;
            }}
            QComboBox#langCombo QAbstractItemView {{
                background-color: {self._CLR_SURFACE};
                color: {self._CLR_TEXT};
                selection-background-color: {self._CLR_ACCENT};
            }}
            QPushButton#dlgSaveBtn {{
                background-color: {self._CLR_ACCENT};
                color: #FFFFFF;
                border: none;
                font-size: 10pt;
                font-weight: 600;
                padding: 8px 20px;
                border-radius: 8px;
                min-height: 36px;
            }}
            QPushButton#dlgSaveBtn:hover   {{ background-color: #3A72D4; }}
            QPushButton#dlgSaveBtn:pressed {{ background-color: #2A5BB0; }}
            QPushButton#dlgSaveBtn:focus   {{
                outline: none;
                border: 2px dashed #FFD700;
            }}
            QPushButton#dlgCancelBtn {{
                background-color: transparent;
                color: {self._CLR_SUBTEXT};
                border: 1px solid {self._CLR_BORDER};
                font-size: 10pt;
                padding: 8px 20px;
                border-radius: 8px;
                min-height: 36px;
            }}
            QPushButton#dlgCancelBtn:hover   {{ color: {self._CLR_TEXT}; border-color: {self._CLR_TEXT}; }}
            QPushButton#dlgCancelBtn:focus   {{
                outline: none;
                border: 2px dashed #FFD700;
            }}
        """)

    # ------------------------------------------------------------------
    # Slot
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Apply the selected language and show a confirmation notice."""
        selected_lang = self._lang_combo.currentData()
        translator.switch_language(selected_lang)

        # Update the dialog's own texts to reflect the new language
        self.setWindowTitle(translator.t("settings_dialog.title"))
        self._lang_label.setText(translator.t("settings_dialog.language_label"))
        self._save_btn.setText(translator.t("settings_dialog.save_button"))
        self._cancel_btn.setText(translator.t("settings_dialog.cancel_button"))

        self._notice_label.setText(translator.t("settings_dialog.restart_notice"))
        self._notice_label.setVisible(True)
