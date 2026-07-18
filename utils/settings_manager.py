"""
utils/settings_manager.py

Manages user settings persisted in logs/settings.json.

Responsibilities:
- Detect the OS language on first launch.
- Default to Turkish if OS is Turkish, otherwise English.
- Once the user manually selects a language, the OS detection is never applied again.
- Expose get_language(), set_language(), and is_manual_set() helpers.
"""

from __future__ import annotations

import json
import locale
import os

# ---------------------------------------------------------------------------
# Path setup — settings file lives in the logs/ folder next to this project
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_LOGS_DIR = os.path.join(_PROJECT_ROOT, "logs")
_SETTINGS_PATH = os.path.join(_LOGS_DIR, "settings.json")

_SUPPORTED_LANGUAGES: list[str] = ["tr", "en"]

# All language codes that EasyOCR supports and that the UI exposes.
# The list is ordered: the first entry is used as the primary language.
_SUPPORTED_OCR_LANGUAGES: list[str] = [
    "tr", "en", "de", "fr", "es", "it", "pt", "ru", "ar", "zh_sim", "zh_tra", "ja", "ko",
]
_DEFAULT_FALLBACK = "en"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_logs_dir() -> None:
    """Create the logs directory if it does not already exist."""
    os.makedirs(_LOGS_DIR, exist_ok=True)


def _load_settings() -> dict:
    """Read settings from disk. Returns an empty dict if the file is missing or corrupt."""
    _ensure_logs_dir()
    if not os.path.exists(_SETTINGS_PATH):
        return {}
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_settings(data: dict) -> None:
    """Persist the settings dict to disk atomically."""
    _ensure_logs_dir()
    try:
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass  # If saving fails silently, the app still works in-memory


def _detect_os_language() -> str:
    """
    Detect the operating system's display language.
    Returns 'tr' if Turkish, otherwise falls back to 'en'.
    """
    try:
        # locale.getdefaultlocale() returns e.g. ('tr_TR', 'cp1254') on Windows
        lang_code, _ = locale.getdefaultlocale()
        if lang_code and lang_code.lower().startswith("tr"):
            return "tr"
    except Exception:
        pass
    return _DEFAULT_FALLBACK


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_language() -> str:
    """
    Return the active language code ('tr' or 'en').

    On the very first call (no settings file found), the OS language is
    detected, saved, and returned. Once the user has manually chosen a
    language, the OS detection is never used again.
    """
    settings = _load_settings()

    if "language" not in settings:
        # First launch: detect from OS
        detected = _detect_os_language()
        settings["language"] = detected
        settings["manual_language_set"] = False
        _save_settings(settings)
        return detected

    lang = settings.get("language", _DEFAULT_FALLBACK)
    return lang if lang in _SUPPORTED_LANGUAGES else _DEFAULT_FALLBACK


def set_language(lang: str) -> None:
    """
    Persist a user-chosen language and mark it as manually set so that
    OS-based detection is never applied again.

    Args:
        lang: A supported language code, e.g. 'tr' or 'en'.
    """
    if lang not in _SUPPORTED_LANGUAGES:
        return
    settings = _load_settings()
    settings["language"] = lang
    settings["manual_language_set"] = True
    _save_settings(settings)


def is_manual_set() -> bool:
    """Return True if the user has ever explicitly chosen a language."""
    settings = _load_settings()
    return bool(settings.get("manual_language_set", False))


def get_ocr_languages() -> list[str]:
    """
    Return the list of EasyOCR language codes selected by the user.

    Defaults to the active UI language when no explicit choice has been saved.
    """
    settings = _load_settings()
    saved = settings.get("ocr_languages")
    if isinstance(saved, list) and saved:
        # Validate: keep only known codes, preserve order
        valid = [c for c in saved if c in _SUPPORTED_OCR_LANGUAGES]
        if valid:
            return valid

    return [get_language()]


def set_ocr_languages(langs: list[str]) -> None:
    """
    Persist the user's EasyOCR language selection.

    Args:
        langs: Non-empty list of EasyOCR language codes.
               Unknown codes are silently dropped.
    """
    valid = [c for c in langs if c in _SUPPORTED_OCR_LANGUAGES]
    if not valid:
        return  # Do not persist an empty selection
    settings = _load_settings()
    settings["ocr_languages"] = valid
    _save_settings(settings)


def get_settings_path() -> str:
    """Return the absolute path to the settings file (useful for debugging)."""
    return _SETTINGS_PATH
