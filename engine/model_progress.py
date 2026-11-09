"""
engine/model_progress.py

Download-progress capture for third-party model downloads.

EasyOCR, Pix2Text, CnOCR/CnSTD and huggingface_hub download their weights on
first use and only report progress to the console. This module hooks into
them so the OCR worker can forward byte-level progress to the UI:

- EasyOCR: `easyocr.easyocr.download_and_unzip` is replaced by an equivalent
  that passes a reporthook to urlretrieve.
- Everything tqdm-based (huggingface_hub, cnocr/cnstd): `tqdm.std.tqdm.display`
  is wrapped at class level, so every subclass and every module that already
  did `from tqdm import tqdm` is covered.

Hooks are inert unless a `capture_downloads()` block is active. While active,
cancellation raises DownloadCancelled from inside the download loop.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Callable

from logger import app_logger

# callback(label, downloaded_bytes, total_bytes) — total 0 means unknown.
ProgressCallback = Callable[[str, int, int], None]


class DownloadCancelled(BaseException):
    """
    Raised inside a download loop when the user cancels.

    Derives from BaseException on purpose: EasyOCR / Pix2Text / huggingface_hub
    wrap downloads in `except Exception` retry-and-fallback blocks, which would
    otherwise swallow the cancellation and start the next mirror / backend.
    """


# tqdm unit → bytes multiplier. Non-byte bars (e.g. "Fetching 5 files",
# batch loops) are ignored.
_BYTE_UNITS = {"B": 1, "iB": 1, "KB": 1024, "kB": 1024, "KiB": 1024}

_MIN_INTERVAL = 0.15  # seconds between UI updates per bar


class _Reporter:
    def __init__(self, callback: ProgressCallback, is_cancelled: Callable[[], bool]) -> None:
        self._callback = callback
        self._is_cancelled = is_cancelled
        self._last: dict[object, float] = {}
        self._lock = threading.Lock()

    def report(self, key: object, label: str, done: int, total: int, *, may_raise: bool = True) -> None:
        if may_raise and self._is_cancelled():
            raise DownloadCancelled()
        now = time.monotonic()
        finished = total > 0 and done >= total
        with self._lock:
            if not finished and now - self._last.get(key, 0.0) < _MIN_INTERVAL:
                return
            self._last[key] = now
        try:
            self._callback(label, int(done), int(total))
        except Exception:  # a UI callback must never break a download
            app_logger.opt(exception=True).debug("Download progress callback failed")


_active: _Reporter | None = None
_install_lock = threading.Lock()
_installed: set[str] = set()


# ---------------------------------------------------------------------------
# tqdm hook
# ---------------------------------------------------------------------------

def _install_tqdm_hook() -> bool:
    try:
        from tqdm.std import tqdm as tqdm_cls
    except ImportError:
        return False

    orig_display = tqdm_cls.display
    orig_close = tqdm_cls.close

    def display(self, msg=None, pos=None):
        reporter = _active
        if reporter is not None and not getattr(self, "disable", False):
            scale = _BYTE_UNITS.get(getattr(self, "unit", ""))
            if scale is not None:
                label = (getattr(self, "desc", "") or "").strip().rstrip(":")
                reporter.report(
                    id(self),
                    label,
                    int((self.n or 0) * scale),
                    int((self.total or 0) * scale),
                    # Never raise while the bar is closing (close()/__del__).
                    may_raise=not getattr(self, "_sb_closing", False),
                )
        return orig_display(self, msg, pos)

    def close(self):
        self._sb_closing = True
        return orig_close(self)

    tqdm_cls.display = display
    tqdm_cls.close = close
    return True


# ---------------------------------------------------------------------------
# EasyOCR hook
# ---------------------------------------------------------------------------

def _install_easyocr_hook() -> bool:
    try:
        import easyocr.easyocr as easyocr_module
    except (ImportError, OSError):
        return False

    def download_and_unzip(url, filename, model_storage_directory, verbose=True):
        from urllib.request import urlretrieve
        from zipfile import ZipFile

        zip_path = os.path.join(model_storage_directory, "temp.zip")
        app_logger.info("Downloading EasyOCR model {} from {}", filename, url)

        def reporthook(block_num: int, block_size: int, total_size: int) -> None:
            reporter = _active
            if reporter is None:
                return
            done = block_num * block_size
            if total_size > 0:
                done = min(done, total_size)
            reporter.report(("easyocr", filename), filename, done, max(total_size, 0))

        try:
            urlretrieve(url, zip_path, reporthook=reporthook)
            with ZipFile(zip_path, "r") as zip_obj:
                zip_obj.extract(filename, model_storage_directory)
        finally:
            try:
                os.remove(zip_path)
            except OSError:
                pass
        app_logger.info("EasyOCR model {} downloaded", filename)

    easyocr_module.download_and_unzip = download_and_unzip
    return True


def install_hooks() -> None:
    """Install all download hooks (idempotent, cheap after the first call)."""
    with _install_lock:
        for name, installer in (("tqdm", _install_tqdm_hook), ("easyocr", _install_easyocr_hook)):
            if name not in _installed and installer():
                _installed.add(name)


@contextmanager
def capture_downloads(callback: ProgressCallback, is_cancelled: Callable[[], bool]):
    """Forward download progress to *callback* for the duration of the block."""
    global _active
    install_hooks()
    _active = _Reporter(callback, is_cancelled)
    try:
        yield
    finally:
        _active = None
