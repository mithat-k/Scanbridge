"""
utils/i18n.py

Translation manager — the single source of truth for all UI strings.

Usage:
    from utils.i18n import translator

    # Retrieve a translated string
    label = translator.t("buttons.select_and_convert")

    # Format a string with placeholders
    msg = translator.t("status.processing", filename="report.pdf")

    # Connect to language changes for live UI updates
    translator.language_changed.connect(self.retranslate_ui)

    # Switch language at runtime
    translator.switch_language("en")
"""

from __future__ import annotations

import json
import os

from PyQt6.QtCore import QObject, pyqtSignal

from utils import settings_manager

# ---------------------------------------------------------------------------
# Locale file path
# ---------------------------------------------------------------------------

_LOCALES_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "locales")


def _load_locale(lang: str) -> dict:
    """
    Load and return the JSON translation table for the given language code.
    Falls back to 'en' if the file for the requested language is missing.
    """
    path = os.path.join(_LOCALES_DIR, f"{lang}.json")
    if not os.path.exists(path):
        path = os.path.join(_LOCALES_DIR, "en.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Translator singleton
# ---------------------------------------------------------------------------

class _Translator(QObject):
    """
    Singleton PyQt6 QObject that holds the current locale data and emits
    a signal whenever the active language is switched, allowing connected
    UI components to update themselves without an application restart.
    """

    # Signal emitted with the new language code whenever the language changes
    language_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lang: str = settings_manager.get_language()
        self._strings: dict = _load_locale(self._lang)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_language(self) -> str:
        """The active language code (e.g. 'tr', 'en')."""
        return self._lang

    def t(self, key: str, **kwargs) -> str:
        """
        Retrieve a translated string by its dot-separated key.

        Args:
            key:    Dot-separated key, e.g. "buttons.select_and_convert".
            kwargs: Named placeholders to format into the string, e.g.
                    translator.t("status.processing", filename="doc.pdf")

        Returns:
            The translated (and formatted) string, or the key itself if not found.
        """
        parts = key.split(".")
        value = self._strings
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part, None)
            else:
                value = None
                break

        if value is None:
            return key  # Graceful degradation: return the raw key

        result = str(value)
        if kwargs:
            try:
                result = result.format(**kwargs)
            except (KeyError, ValueError):
                pass  # Return unformatted string if placeholders don't match
        return result

    def switch_language(self, lang: str) -> None:
        """
        Switch the active language at runtime.

        Saves the choice to settings, reloads the string table, then
        emits `language_changed` so all connected UI slots can call
        their `retranslate_ui()` methods.

        Args:
            lang: Language code to switch to ('tr' or 'en').
        """
        if lang == self._lang:
            return
        settings_manager.set_language(lang)
        self._lang = lang
        self._strings = _load_locale(lang)
        self.language_changed.emit(lang)

    def reload(self) -> None:
        """Reload the current locale file from disk (useful after external edits)."""
        self._strings = _load_locale(self._lang)


# ---------------------------------------------------------------------------
# Module-level singleton — import this everywhere
# ---------------------------------------------------------------------------

translator = _Translator()
