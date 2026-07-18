"""
ui/settings_dialog.py

Settings dialog — interface language selector + EasyOCR recognition language picker.

Changes are applied live (interface language) or on the next conversion start
(OCR languages) without requiring an application restart.

EasyOCR language selection uses a QListWidget with Qt.ItemFlag.ItemIsUserCheckable
items so the user can tick multiple languages. The widget is wrapped in a styled
QFrame to match the rest of the dark UI.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFrame,
    QListWidget, QListWidgetItem, QSizePolicy,
)

from utils.i18n import translator
from utils.settings_manager import (
    get_ocr_languages,
    set_ocr_languages,
    _SUPPORTED_OCR_LANGUAGES,  # noqa: WPS450 — intentional internal use
)

# ---------------------------------------------------------------------------
# Ordered list of (easyocr_code, translation_key) pairs exposed in the UI.
# Order matches _SUPPORTED_OCR_LANGUAGES in settings_manager.py.
# ---------------------------------------------------------------------------
_OCR_LANG_ITEMS: list[tuple[str, str]] = [
    ("tr",     "settings_dialog.ocr_lang_tr"),
    ("en",     "settings_dialog.ocr_lang_en"),
    ("de",     "settings_dialog.ocr_lang_de"),
    ("fr",     "settings_dialog.ocr_lang_fr"),
    ("es",     "settings_dialog.ocr_lang_es"),
    ("it",     "settings_dialog.ocr_lang_it"),
    ("pt",     "settings_dialog.ocr_lang_pt"),
    ("ru",     "settings_dialog.ocr_lang_ru"),
    ("ar",     "settings_dialog.ocr_lang_ar"),
    ("zh_sim", "settings_dialog.ocr_lang_zh_sim"),
    ("zh_tra", "settings_dialog.ocr_lang_zh_tra"),
    ("ja",     "settings_dialog.ocr_lang_ja"),
    ("ko",     "settings_dialog.ocr_lang_ko"),
]


class SettingsDialog(QDialog):
    """
    Modal settings dialog with:
    - Interface language selector (QComboBox).
    - EasyOCR recognition language picker (multi-select QListWidget).

    The interface language change is applied immediately via the Translator.
    The OCR language change is saved to settings.json and used on the next
    conversion start (OCRWorker reads it fresh each time it initialises).
    """

    # Color palette — aligned with MainWindow for visual consistency
    _CLR_BG      = "#0F0F0F"
    _CLR_SURFACE = "#1A1A2E"
    _CLR_ACCENT  = "#4F8EF7"
    _CLR_TEXT    = "#E8E8F0"
    _CLR_SUBTEXT = "#A0A0B0"
    _CLR_BORDER  = "#2E2E4E"
    _CLR_WARNING = "#FFC107"
    _CLR_SUCCESS = "#4CAF50"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(400)
        self._build_ui()
        self._apply_stylesheet()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(translator.t("settings_dialog.title"))
        self.setAccessibleName(translator.t("settings_dialog.title"))

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(20)

        # ── Interface language row ────────────────────────────────────
        lang_row = QHBoxLayout()
        lang_row.setSpacing(16)

        self._lang_label = QLabel(translator.t("settings_dialog.language_label"))
        self._lang_label.setObjectName("settingsLabel")

        self._lang_combo = QComboBox()
        self._lang_combo.setObjectName("langCombo")
        self._lang_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._lang_combo.setAccessibleName(translator.t("settings_dialog.language_label"))
        self._lang_combo.addItem(translator.t("settings_dialog.language_tr"), "tr")
        self._lang_combo.addItem(translator.t("settings_dialog.language_en"), "en")

        # Pre-select the currently active language
        current = translator.current_language
        idx = self._lang_combo.findData(current)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)

        lang_row.addWidget(self._lang_label)
        lang_row.addWidget(self._lang_combo, stretch=1)
        root.addLayout(lang_row)

        # ── OCR language section ──────────────────────────────────────
        self._ocr_label = QLabel(translator.t("settings_dialog.ocr_lang_label"))
        self._ocr_label.setObjectName("settingsLabel")
        root.addWidget(self._ocr_label)

        # QListWidget with checkable items — acts as a multi-select combobox
        self._ocr_list = QListWidget()
        self._ocr_list.setObjectName("ocrLangList")
        self._ocr_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._ocr_list.setAccessibleName(translator.t("settings_dialog.ocr_lang_label"))
        self._ocr_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # Show all items without a scrollbar (max 6 visible rows, rest scrollable)
        self._ocr_list.setFixedHeight(min(len(_OCR_LANG_ITEMS), 6) * 32 + 4)

        currently_selected: list[str] = get_ocr_languages()

        for code, key in _OCR_LANG_ITEMS:
            label = translator.t(key)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_state = (
                Qt.CheckState.Checked
                if code in currently_selected
                else Qt.CheckState.Unchecked
            )
            item.setCheckState(check_state)
            self._ocr_list.addItem(item)

        root.addWidget(self._ocr_list)

        # Hint text below the list
        self._ocr_hint = QLabel(translator.t("settings_dialog.ocr_lang_hint"))
        self._ocr_hint.setObjectName("hintLabel")
        self._ocr_hint.setWordWrap(True)
        root.addWidget(self._ocr_hint)

        # ── Notice label (confirmation / warning) ─────────────────────
        self._notice_label = QLabel("")
        self._notice_label.setObjectName("noticeLabel")
        self._notice_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notice_label.setWordWrap(True)
        self._notice_label.setVisible(False)
        root.addWidget(self._notice_label)

        # ── Separator ─────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        root.addWidget(sep)

        # ── Action buttons ────────────────────────────────────────────
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
            QLabel#hintLabel {{
                font-size: 9pt;
                color: {self._CLR_SUBTEXT};
                padding: 2px 0 0 0;
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

            /* Interface language combobox */
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
            QComboBox#langCombo:focus {{
                outline: none;
                border: 2px dashed #FFD700;
            }}

            /* OCR language list */
            QListWidget#ocrLangList {{
                background-color: {self._CLR_SURFACE};
                color: {self._CLR_TEXT};
                border: 1px solid {self._CLR_BORDER};
                border-radius: 6px;
                padding: 4px 2px;
                font-size: 10pt;
                outline: none;
            }}
            QListWidget#ocrLangList::item {{
                padding: 5px 8px;
                border-radius: 4px;
            }}
            QListWidget#ocrLangList::item:selected {{
                background-color: transparent;
                color: {self._CLR_TEXT};
            }}
            QListWidget#ocrLangList::item:hover {{
                background-color: rgba(79, 142, 247, 0.12);
            }}
            QListWidget#ocrLangList:focus {{
                border: 2px dashed #FFD700;
            }}

            /* Buttons */
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
    # Helpers
    # ------------------------------------------------------------------

    def _get_checked_ocr_languages(self) -> list[str]:
        """Return the EasyOCR codes for all checked items in the list."""
        result: list[str] = []
        for i in range(self._ocr_list.count()):
            item = self._ocr_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                code = item.data(Qt.ItemDataRole.UserRole)
                if code:
                    result.append(code)
        return result

    # ------------------------------------------------------------------
    # Slot
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """
        Save both the interface language and the OCR language selection.

        Interface language: applied immediately via Translator.
        OCR languages: persisted to settings.json; takes effect on the next
        conversion (OCRWorker reads them fresh at initialisation time).
        """
        # --- Interface language ---
        selected_lang = self._lang_combo.currentData()
        translator.switch_language(selected_lang)

        # Refresh this dialog's own texts to match the new language
        self.setWindowTitle(translator.t("settings_dialog.title"))
        self._lang_label.setText(translator.t("settings_dialog.language_label"))
        self._ocr_label.setText(translator.t("settings_dialog.ocr_lang_label"))
        self._ocr_hint.setText(translator.t("settings_dialog.ocr_lang_hint"))
        self._save_btn.setText(translator.t("settings_dialog.save_button"))
        self._cancel_btn.setText(translator.t("settings_dialog.cancel_button"))

        # --- OCR languages ---
        ocr_langs = self._get_checked_ocr_languages()
        if ocr_langs:
            set_ocr_languages(ocr_langs)
            # Invalidate the cached EasyOCR reader so it reloads with the new
            # language list on the next conversion.
            from engine.ocr_worker import OCRWorker
            OCRWorker._reader = None
            OCRWorker._reader_langs = None

        # --- Show notice ---
        notice_parts: list[str] = [translator.t("settings_dialog.restart_notice")]
        if ocr_langs:
            notice_parts.append(translator.t("settings_dialog.ocr_lang_changed_notice"))

        self._notice_label.setText("  ".join(notice_parts))
        self._notice_label.setVisible(True)
