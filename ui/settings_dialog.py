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
    QSizePolicy,
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

        ocr_row = QHBoxLayout()
        ocr_row.setSpacing(16)

        self._ocr_combo1 = QComboBox()
        self._ocr_combo1.setObjectName("ocrCombo1")
        self._ocr_combo1.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._ocr_combo1.setAccessibleName(translator.t("settings_dialog.ocr_lang_label") + " 1")

        self._ocr_combo2 = QComboBox()
        self._ocr_combo2.setObjectName("ocrCombo2")
        self._ocr_combo2.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._ocr_combo2.setAccessibleName(translator.t("settings_dialog.ocr_lang_label") + " 2")

        # Add "None" option to the second combobox
        self._ocr_combo2.addItem(translator.t("settings_dialog.ocr_lang_none"), "")

        for code, key in _OCR_LANG_ITEMS:
            label = translator.t(key)
            self._ocr_combo1.addItem(label, code)
            self._ocr_combo2.addItem(label, code)

        currently_selected: list[str] = get_ocr_languages()

        if currently_selected:
            idx1 = self._ocr_combo1.findData(currently_selected[0])
            if idx1 >= 0:
                self._ocr_combo1.setCurrentIndex(idx1)

            if len(currently_selected) > 1:
                idx2 = self._ocr_combo2.findData(currently_selected[1])
                if idx2 >= 0:
                    self._ocr_combo2.setCurrentIndex(idx2)
            else:
                self._ocr_combo2.setCurrentIndex(0) # None

        ocr_row.addWidget(self._ocr_combo1, stretch=1)
        ocr_row.addWidget(self._ocr_combo2, stretch=1)
        root.addLayout(ocr_row)

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

            /* Interface & OCR language comboboxes */
            QComboBox#langCombo, QComboBox#ocrCombo1, QComboBox#ocrCombo2 {{
                background-color: {self._CLR_SURFACE};
                color: {self._CLR_TEXT};
                border: 1px solid {self._CLR_BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 10pt;
                min-height: 32px;
            }}
            QComboBox#langCombo::drop-down, QComboBox#ocrCombo1::drop-down, QComboBox#ocrCombo2::drop-down {{
                border: none;
            }}
            QComboBox#langCombo QAbstractItemView, QComboBox#ocrCombo1 QAbstractItemView, QComboBox#ocrCombo2 QAbstractItemView {{
                background-color: {self._CLR_SURFACE};
                color: {self._CLR_TEXT};
                selection-background-color: {self._CLR_ACCENT};
            }}
            QComboBox#langCombo:focus, QComboBox#ocrCombo1:focus, QComboBox#ocrCombo2:focus {{
                outline: none;
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
        """Return the EasyOCR codes from the two comboboxes."""
        result: list[str] = []
        code1 = self._ocr_combo1.currentData()
        if code1:
            result.append(code1)
        code2 = self._ocr_combo2.currentData()
        if code2 and code2 != code1:
            result.append(code2)
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
