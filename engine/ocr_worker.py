"""
engine/ocr_worker.py

Background OCR worker thread — includes CPU and GPU optimizations.

Converts a PDF file into an accessible HTML document by:
1. Scanning every page for watermarks / repeated text (Phase 1).
2. Running EasyOCR for plain-text pages and Pix2Text for pages with math
   formulae (Phase 2).
3. Compiling the results into a navigable HTML document with MathML support
   via Pandoc.

All user-visible strings are retrieved from the Translator so the worker
respects the active language at runtime.
"""

from __future__ import annotations

import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from engine.model_progress import DownloadCancelled, capture_downloads
from logger import app_logger
from utils.i18n import translator
from utils.settings_manager import get_ocr_languages

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Regex for detecting real LaTeX / formula symbols — avoids false positives.
_MATH_RE = re.compile(r"[=\^_\\{}]|\$|\bfrac\b|\bsqrt\b|\bsum\b|\bint\b")

# Normalized strings shorter than this are never considered watermarks.
_MIN_WATERMARK_LEN = 4


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def _check_dependencies() -> list[str]:
    """Return a list of pip package names for any missing required modules."""
    missing: list[str] = []
    required = [
        ("fitz", "PyMuPDF"),
        ("bs4", "beautifulsoup4"),
        ("pypandoc", "pypandoc"),
        ("easyocr", "easyocr"),
        # Pix2Text 1.1 imports optimum.onnxruntime at module level and CnOCR
        # runs its text models on ONNX Runtime, so it is a hard requirement.
        ("onnxruntime", "onnxruntime"),
        ("pix2text", "pix2text"),
        ("numpy", "numpy"),
        ("PIL", "pillow"),
        ("cv2", "opencv-python"),
    ]
    for mod, pip_name in required:
        try:
            __import__(mod)
        except (ImportError, OSError):
            missing.append(pip_name)
    return missing


# ---------------------------------------------------------------------------
# ONNX Runtime detection
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def detect_onnxruntime() -> dict:
    """
    Look for ONNX Runtime and report what it can run on.

    Returns a dict:
        available (bool)        – onnxruntime imports cleanly
        version   (str | None)
        providers (list[str])   – ort.get_available_providers()
        cuda      (bool)        – CUDAExecutionProvider present (onnxruntime-gpu)
        directml  (bool)        – DmlExecutionProvider present (onnxruntime-directml)

    Cached for the session; safe to call from any thread. Kept module-level so
    the health checker can reuse it.
    """
    info: dict = {
        "available": False,
        "version": None,
        "providers": [],
        "cuda": False,
        "directml": False,
    }
    try:
        import onnxruntime as ort
    except (ImportError, OSError) as exc:
        app_logger.warning("ONNX Runtime not available: {}", exc)
        return info

    providers = list(ort.get_available_providers())
    info.update(
        available=True,
        version=getattr(ort, "__version__", None),
        providers=providers,
        cuda="CUDAExecutionProvider" in providers,
        directml="DmlExecutionProvider" in providers,
    )
    app_logger.info(
        "ONNX Runtime {} found, providers: {}", info["version"], ", ".join(providers) or "-"
    )
    return info


def _pix2text_attempts(device: str) -> list[tuple[str, dict]]:
    """
    Ordered (description, total_configs) attempts for Pix2Text.from_config,
    chosen from the ONNX Runtime capabilities.

    Every sub-model of TextFormulaOCR is configured explicitly (keys live under
    total_configs["text_formula"]; top-level keys are silently ignored):
        text    – CnOCR detector + recognizer (det/rec_model_backend)
        mfd     – formula detector (YOLO). "mfd-1.5" exists only as ONNX; the
                  PyTorch fallback uses the older "mfd" model.
        formula – formula recognizer (MFR). An explicit ORT provider is passed
                  so ONNX never picks an unusable one.
    The layout model (DocLayout-YOLO) is PyTorch-only in Pix2Text 1.1.
    """
    ort = detect_onnxruntime()
    pytorch = (
        "pytorch",
        {"text_formula": {
            "text": {"det_model_backend": "pytorch", "rec_model_backend": "pytorch"},
            "mfd": {"model_name": "mfd", "model_backend": "pytorch"},
            "formula": {"model_backend": "pytorch"},
        }},
    )

    if not ort["available"]:
        return [pytorch]

    def onnx(provider: str) -> tuple[str, dict]:
        return (
            f"onnx/{provider}",
            {"text_formula": {
                "text": {"det_model_backend": "onnx", "rec_model_backend": "onnx"},
                "mfd": {"model_name": "mfd-1.5", "model_backend": "onnx"},
                "formula": {
                    "model_backend": "onnx",
                    "more_model_configs": {"provider": provider},
                },
            }},
        )

    if device == "cuda":
        if ort["cuda"]:
            return [onnx("CUDAExecutionProvider"), pytorch, onnx("CPUExecutionProvider")]
        # The CPU build of onnxruntime cannot use the GPU — PyTorch can.
        app_logger.info(
            "ONNX Runtime has no CUDAExecutionProvider (install onnxruntime-gpu for "
            "GPU ONNX inference); preferring the PyTorch backend on CUDA."
        )
        return [pytorch, onnx("CPUExecutionProvider")]

    return [onnx("CPUExecutionProvider"), pytorch]


# ---------------------------------------------------------------------------
# Pixmap → PIL / NumPy conversions (in-memory — no disk I/O)
# ---------------------------------------------------------------------------

def _pixmap_to_pil(pix):
    """
    Convert a PyMuPDF Pixmap to a PIL Image without writing to disk.

    Compatibility notes:
    - pix.samples may be bytes or memoryview → cast with bytes().
    - CMYK / Grayscale colour spaces are normalized to RGB.
    - Alpha channel is stripped.
    """
    from PIL import Image
    import fitz

    # Normalize non-RGB colour spaces to RGB
    if pix.colorspace and pix.colorspace.n != 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)

    # Strip alpha channel (colour-space conversion above keeps alpha intact)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)  # 0 = drop alpha

    raw = bytes(pix.samples)
    return Image.frombytes("RGB", (pix.width, pix.height), raw)


def _pil_to_numpy(img):
    """Convert a PIL Image to a uint8 NumPy array (compatible with EasyOCR)."""
    import numpy as np
    return np.asarray(img, dtype=np.uint8)


def _denoise(pil_img):
    """
    Apply OpenCV fastNlMeansDenoisingColored noise reduction.
    Returns the original image unchanged if cv2 is unavailable.
    """
    try:
        import cv2
        import numpy as np

        img_np = np.asarray(pil_img, dtype=np.uint8)
        bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

        denoised = cv2.fastNlMeansDenoisingColored(
            bgr, None,
            h=10, hColor=10,
            templateWindowSize=7,
            searchWindowSize=21,
        )

        rgb = cv2.cvtColor(denoised, cv2.COLOR_BGR2RGB)
        from PIL import Image
        return Image.fromarray(rgb)
    except Exception:
        return pil_img


# ---------------------------------------------------------------------------
# OpenCV visual cleaning (RULES.MD rule 5 — watermark suppression)
# ---------------------------------------------------------------------------

def _clean_image_opencv(pil_img):
    """
    Remove faint watermarks and logos using OpenCV grayscale conversion
    and Otsu's binarisation, producing a high-contrast clean image.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        img_np = np.array(pil_img)

        # Convert to grayscale
        if len(img_np.shape) == 3:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_np

        # Smooth while preserving edges with a bilateral filter
        smoothed = cv2.bilateralFilter(gray, 9, 75, 75)

        # Dynamic thresholding via Otsu's method — reliably removes watermarks
        _, thresh = cv2.threshold(smoothed, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

        return Image.fromarray(cv2.cvtColor(thresh, cv2.COLOR_GRAY2RGB))
    except Exception:
        return pil_img


# ---------------------------------------------------------------------------
# Text cleaning helpers (RULES.MD rule 5 — noise / watermark filtering)
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """
    Normalize a text string for watermark comparison.
    Lowercases, strips numbers, and removes non-alphanumeric characters
    (Turkish characters are preserved).
    """
    t = text.lower().strip()
    t = re.sub(r'\b\d+\b', '', t)
    t = re.sub(r'[^a-z0-9çğöşüıiâêîûô]', '', t)
    return t


def _is_meaningless(text: str) -> bool:
    """
    Return True if the OCR output is noise (meaningless character sequences).

    Criteria:
    - Empty string.
    - No alphanumeric characters at all.
    - Consecutive repeated symbol noise (e.g. ||||, -----, .....).
    - Any single word longer than 30 characters (likely an OCR artefact).
    """
    t = text.strip()
    if not t:
        return True

    if not re.search(r'[a-zA-Z0-9çğöşüıIİÂÊÎÛÔ]', t):
        return True

    if re.search(r'([|._\-\*\^~])\1{2,}', t):
        return True

    words = t.split()
    if any(len(w) > 30 for w in words):
        return True

    return False


# ---------------------------------------------------------------------------
# HTML template — RULES.MD rule 6: inactive pages hidden from screen readers
# ---------------------------------------------------------------------------

def _build_html_template(total_pages: int) -> str:
    """
    Build a navigable HTML shell with per-page navigation buttons.
    Page 1 is visible; all other pages are aria-hidden and display:none.
    """
    nav_buttons = "\n  ".join(
        f'<button onclick="showPage({i+1})" aria-label="Page {i+1}">{i+1}</button>'
        for i in range(total_pages)
    )
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scanbridge Output</title>
<style>
  .hidden-page {{ display: none; }}
  nav {{ padding: 8px; text-align: center; }}
  nav button {{ margin: 2px; padding: 4px 10px; cursor: pointer; }}
</style>
<script>
  function showPage(pageNum) {{
      document.querySelectorAll('section[id^="page-"]').forEach(function(s) {{
          s.classList.add('hidden-page');
          s.setAttribute('aria-hidden', 'true');
          s.style.display = 'none';
      }});
      var active = document.getElementById('page-' + pageNum);
      if (active) {{
          active.classList.remove('hidden-page');
          active.removeAttribute('aria-hidden');
          active.style.display = '';
      }}
  }}
</script>
</head>
<body>
<nav aria-label="Page navigation">
  {nav_buttons}
</nav>
<main id="content"></main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# OCR worker thread
# ---------------------------------------------------------------------------

class OCRWorker(QThread):
    """
    Background thread that converts a PDF file to an accessible HTML document.

    Signals
    -------
    progress     : (int, str)  – percentage [0–100] and a status message
    result_ready : str         – absolute path to the output HTML file
    error        : str         – error message (status.cancel_sentinel on cancel)
    models_loading    : str    – a model is being loaded / downloaded (not cached);
                                 emitted once per model with a status message
    download_progress : (str, int, int) – file label, bytes done, bytes total (0 = unknown)
    models_ready      : —      – model preparation ended (always follows models_loading)
    """

    progress = pyqtSignal(int, str)
    result_ready = pyqtSignal(str)
    error    = pyqtSignal(str)
    models_loading    = pyqtSignal(str)
    # `object` instead of int: Qt's int is 32-bit and model files can exceed 2 GiB.
    download_progress = pyqtSignal(str, object, object)
    models_ready      = pyqtSignal()

    # Class-level model cache (RULES.MD: models are kept alive for the session)
    _reader      = None
    _p2t         = None
    _reader_gpu  = None
    _reader_langs: list[str] | None = None  # Cached language list for invalidation
    _p2t_device  = None

    def __init__(
        self,
        pdf_path: str,
        gpu_enabled: bool = False,
        device_type: str = "cpu",
    ) -> None:
        super().__init__()
        self.pdf_path    = pdf_path
        self.output_path = str(Path(pdf_path).with_suffix(".html"))
        self.gpu_enabled = gpu_enabled
        self.device_type = device_type
        self._cancelled  = False

    def cancel(self) -> None:
        """Signal the worker to stop after the current page completes."""
        self._cancelled = True

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        app_logger.info(translator.t("log.ocr_started", path=self.pdf_path))
        try:
            if self._process():
                app_logger.info(translator.t("log.ocr_done"))
        except DownloadCancelled:
            app_logger.info("Model download cancelled by the user")
            self._emit_cancelled()
        except Exception as exc:
            app_logger.opt(exception=True).error(translator.t("log.ocr_error", error=str(exc)))
            self.error.emit(str(exc))

    def _emit_cancelled(self) -> None:
        # MainWindow._on_error ignores exactly this string — the UI was already
        # reset by _on_cancel_clicked.
        self.error.emit(translator.t("status.cancel_sentinel"))

    def _process(self) -> bool:
        """Run the conversion. Returns True only if the output file was written."""
        self.progress.emit(5, translator.t("progress.checking_libs"))

        missing = _check_dependencies()
        if missing:
            libs = ", ".join(missing)
            self.error.emit(translator.t("errors.missing_libs", libs=libs))
            return False

        import fitz
        from bs4 import BeautifulSoup
        import pypandoc

        self.progress.emit(8, translator.t("progress.preparing_models"))
        reader, p2t = self._get_models()
        if self._cancelled:
            self._emit_cancelled()
            return False

        self.progress.emit(10, translator.t("progress.opening_pdf"))

        doc = fitz.open(self.pdf_path)
        try:
            total = len(doc)

            if total == 0:
                self.error.emit(translator.t("errors.empty_pdf"))
                return False

            # ── Phase 1: Watermark and repeated-text detection ──
            self.progress.emit(12, translator.t("progress.phase1"))
            raw_page_results = []
            normalized_counts: dict[str, int] = {}

            for i, page in enumerate(doc):
                if self._cancelled:
                    self._emit_cancelled()
                    return False

                pct = int(12 + (i / total) * 33)
                self.progress.emit(
                    pct,
                    translator.t("progress.phase1_page", current=i + 1, total=total),
                )

                # In-memory image pipeline (no disk writes during OCR)
                pix = page.get_pixmap(dpi=150)
                pil_img = _pixmap_to_pil(pix)
                del pix

                cleaned_pil = _clean_image_opencv(pil_img)
                del pil_img

                cleaned_pil = _denoise(cleaned_pil)

                # Run EasyOCR
                np_img = _pil_to_numpy(cleaned_pil)
                results = reader.readtext(np_img)
                del np_img
                del cleaned_pil

                raw_page_results.append(results)

                # Count unique normalized strings per page for watermark detection
                seen_on_page: set[str] = set()
                for _, text, _ in results:
                    norm = _normalize_text(text)
                    # Very short fragments ("ve", "a", "x") recur on most pages
                    # as ordinary content — never treat them as watermarks.
                    if len(norm) >= _MIN_WATERMARK_LEN:
                        seen_on_page.add(norm)

                for norm in seen_on_page:
                    normalized_counts[norm] = normalized_counts.get(norm, 0) + 1

            # Watermark set: strings appearing on ≥30% of pages (minimum 2 pages)
            watermarks: set[str] = set()
            if total >= 2:
                threshold = max(2, int(total * 0.3))
                for norm, count in normalized_counts.items():
                    if count >= threshold:
                        watermarks.add(norm)

            # ── Phase 2: HTML generation ──
            self.progress.emit(45, translator.t("progress.phase2"))
            template = _build_html_template(total)
            soup = BeautifulSoup(template, "html.parser")
            main_el = soup.find("main")

            for i, page in enumerate(doc):
                if self._cancelled:
                    self._emit_cancelled()
                    return False

                pct = int(45 + (i / total) * 40)
                self.progress.emit(
                    pct,
                    translator.t("progress.phase2_page", current=i + 1, total=total),
                )

                results = raw_page_results[i]

                if self._has_math(results, watermarks):
                    self.progress.emit(
                        pct,
                        translator.t("progress.formula_detected", current=i + 1, total=total),
                    )
                    pix = page.get_pixmap(dpi=150)
                    pil_img = _pixmap_to_pil(pix)
                    del pix

                    cleaned_pil = _clean_image_opencv(pil_img)
                    del pil_img
                    cleaned_pil = _denoise(cleaned_pil)

                    p2t_res = self._run_p2t(p2t, cleaned_pil)
                    del cleaned_pil

                    section = self._build_math_section(soup, i + 1, p2t_res, watermarks)
                else:
                    section = self._build_text_section(soup, i + 1, results, watermarks)

                main_el.append(section)
        finally:
            doc.close()

        # Pandoc MathML integration — only the formula paragraphs go through
        # Pandoc. Converting the whole document strips the <head> (CSS +
        # showPage script) and the nav buttons' onclick handlers, and Pandoc's
        # HTML reader never parses $$...$$ text as math anyway.
        self.progress.emit(85, translator.t("progress.pandoc_compile"))
        self._convert_formulas_to_mathml(soup, pypandoc)

        self.progress.emit(95, translator.t("progress.building_html"))
        final_html = soup.prettify()

        if self._cancelled:
            self._emit_cancelled()
            return False

        # Final disk write — only the output file (no intermediate disk I/O)
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(final_html)

        self.progress.emit(100, translator.t("progress.done"))
        self.result_ready.emit(self.output_path)
        return True

    @staticmethod
    def _convert_formulas_to_mathml(soup, pypandoc) -> None:
        """
        Replace each `$$ ... $$` formula paragraph's text with Pandoc-generated
        MathML. Paragraphs Pandoc cannot convert keep their `$$` source text.
        """
        from bs4 import BeautifulSoup

        for p in soup.find_all("p", class_="math-formula"):
            tex = p.get_text().strip()
            try:
                converted = pypandoc.convert_text(
                    tex,
                    to="html",
                    format="markdown",
                    extra_args=["--mathml"],
                )
            except Exception as exc:
                app_logger.warning("Pandoc MathML conversion failed: {}", exc)
                continue
            math_el = BeautifulSoup(converted, "html.parser").find("math")
            if math_el is None:
                continue
            p.clear()
            p.append(math_el)

    # ------------------------------------------------------------------
    # Model loading (with session-level cache)
    # ------------------------------------------------------------------

    def _get_models(self):
        """
        Load and cache EasyOCR and Pix2Text models. Re-initialises only on
        device or language change.

        When a model is not cached, `models_loading` is emitted (the UI shows
        the model preparation dialog) and weight downloads are reported via
        `download_progress`. Cancelling aborts a running download.
        """
        import easyocr

        # Read the user's current OCR language selection from settings.
        # This is intentionally re-read on every conversion start so that
        # changes made in the Settings dialog take effect immediately.
        ocr_langs = get_ocr_languages()

        need_reader = (
            OCRWorker._reader is None
            or OCRWorker._reader_gpu != self.gpu_enabled
            or OCRWorker._reader_langs != ocr_langs
        )
        need_p2t = OCRWorker._p2t is None or OCRWorker._p2t_device != self.device_type

        if not (need_reader or need_p2t):
            return OCRWorker._reader, OCRWorker._p2t

        def on_download(label: str, done: int, total: int) -> None:
            self.download_progress.emit(label, done, total)

        try:
            with capture_downloads(on_download, lambda: self._cancelled):
                # EasyOCR — RULES.MD rule 1: never pass `workers` to easyocr.Reader.
                if need_reader:
                    key = "loading.easyocr_gpu" if self.gpu_enabled else "loading.easyocr_cpu"
                    self._announce_model_stage(8, translator.t(key))
                    app_logger.info(
                        "Loading EasyOCR (langs={}, gpu={})", ocr_langs, self.gpu_enabled
                    )
                    OCRWorker._reader = easyocr.Reader(
                        ocr_langs,
                        gpu=self.gpu_enabled,
                        quantize=(not self.gpu_enabled),  # INT8 quantisation on CPU
                        verbose=False,  # download progress is captured by model_progress
                    )
                    OCRWorker._reader_gpu = self.gpu_enabled
                    OCRWorker._reader_langs = list(ocr_langs)

                # Pix2Text — re-initialise if device changed
                if need_p2t and not self._cancelled:
                    self._announce_model_stage(9, translator.t("loading.pix2text"))
                    OCRWorker._p2t = self._load_pix2text(self.device_type)
                    OCRWorker._p2t_device = self.device_type
        finally:
            self.models_ready.emit()

        return OCRWorker._reader, OCRWorker._p2t

    def _announce_model_stage(self, pct: int, message: str) -> None:
        self.progress.emit(pct, message)
        self.models_loading.emit(message)

    @staticmethod
    def _load_pix2text(device: str):
        """
        Load Pix2Text, trying formula backends in the order chosen by
        `_pix2text_attempts()` (ONNX Runtime provider aware), then the legacy
        direct constructor as a last resort.

        DownloadCancelled is a BaseException, so it passes through the
        `except Exception` fallbacks and aborts loading immediately.
        """
        from pix2text import Pix2Text

        for name, configs in _pix2text_attempts(device):
            try:
                app_logger.info("Loading Pix2Text (backend={}, device={})", name, device)
                p2t = Pix2Text.from_config(total_configs=configs, device=device)
                app_logger.info("Pix2Text loaded with backend {}", name)
                return p2t
            except Exception as exc:
                app_logger.opt(exception=True).warning(
                    "Pix2Text could not be loaded with backend {}: {}", name, exc
                )

        app_logger.warning("All Pix2Text configs failed; falling back to direct construction")
        return Pix2Text(device=device)

    # ------------------------------------------------------------------
    # Pix2Text call — RULES.MD rule 2: pass a file path, not a PIL Image
    # ------------------------------------------------------------------

    @staticmethod
    def _run_p2t(p2t, pil_img):
        """
        Call Pix2Text.recognize_page() using a temporary file path.

        RULES.MD rule 2: recognize_page() does not accept a PIL Image directly.
        Write a temp file, pass its path, then delete it immediately.
        """
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
        try:
            os.close(tmp_fd)
            pil_img.save(tmp_path, format="PNG")
            return p2t.recognize_page(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Math detection
    # ------------------------------------------------------------------

    @staticmethod
    def _has_math(results: list, watermarks: set) -> bool:
        """Return True if EasyOCR results contain a significant density of math symbols."""
        if not results:
            return False

        # Filter watermarks and noise before checking for math
        valid_texts = []
        for _, text, prob in results:
            if _is_meaningless(text):
                continue
            norm = _normalize_text(text)
            if norm in watermarks:
                continue
            valid_texts.append((text, prob))

        return any(
            _MATH_RE.search(text) and prob < 0.8
            for text, prob in valid_texts
        )

    # ------------------------------------------------------------------
    # BeautifulSoup section builders
    # RULES.MD rule 6: page 1 visible, all others hidden + aria-hidden
    # ------------------------------------------------------------------

    @staticmethod
    def _build_section_attrs(page_num: int) -> dict:
        """Return the HTML attributes dict for a page section element."""
        attrs = {
            "id": f"page-{page_num}",
            "aria-label": f"Page {page_num}",
        }
        if page_num > 1:
            attrs["class"] = "hidden-page"
            attrs["aria-hidden"] = "true"
            attrs["style"] = "display: none;"
        return attrs

    @staticmethod
    def _build_text_section(soup, page_num: int, results: list, watermarks: set):
        """Build a plain-text page section, filtering noise and watermarks."""
        section = soup.new_tag("section", attrs=OCRWorker._build_section_attrs(page_num))
        for _, text, _ in results:
            if _is_meaningless(text):
                continue
            norm = _normalize_text(text)
            if norm in watermarks:
                continue
            p = soup.new_tag("p")
            p.string = text
            section.append(p)
        return section

    @staticmethod
    def _build_math_section(soup, page_num: int, p2t_res, watermarks: set):
        """
        Build a math-formula page section.

        RULES.MD rule 3: Pix2Text 1.0+ returns a Page object — iterate
        `.elements` instead of the object itself.
        """
        section = soup.new_tag("section", attrs=OCRWorker._build_section_attrs(page_num))

        # RULES.MD rule 3: use .elements list for Pix2Text 1.0+ output
        elements = getattr(p2t_res, "elements", p2t_res)

        # Wrap a non-iterable single Page in a list
        if not hasattr(elements, "__iter__"):
            elements = [elements]

        for item in elements:
            if isinstance(item, dict):
                i_type = str(item.get("type", ""))
                i_text = str(item.get("text", ""))
            else:
                i_type = str(getattr(item, "type", ""))
                i_text = str(getattr(item, "text", ""))

            if _is_meaningless(i_text):
                continue
            norm = _normalize_text(i_text)
            if norm in watermarks:
                continue

            if "formula" in i_type.lower() or "math" in i_type.lower():
                p = soup.new_tag(
                    "p", attrs={"class": "math-formula", "role": "math"}
                )
                p.string = f"$$ {i_text} $$"
            else:
                p = soup.new_tag("p")
                p.string = i_text
            section.append(p)
        return section


# ---------------------------------------------------------------------------
# Startup model preparation
# ---------------------------------------------------------------------------

class ModelPrepWorker(OCRWorker):
    """
    Loads (and on first run downloads) the OCR models right after the health
    check, so the first conversion does not stall on a multi-GB download.

    Reuses OCRWorker's model cache, `_get_models()` and its signals:
        models_loading / download_progress / models_ready – as in OCRWorker
        prepared – models are loaded and cached
        error    – loading failed (status.cancel_sentinel when cancelled)

    cancel() aborts a running download; a model already loading from disk
    finishes first. The models are then loaded by the next conversion.
    """

    prepared = pyqtSignal()

    def __init__(self, gpu_enabled: bool = False, device_type: str = "cpu") -> None:
        QThread.__init__(self)
        self.pdf_path = ""
        self.output_path = ""
        self.gpu_enabled = gpu_enabled
        self.device_type = device_type
        self._cancelled = False

    def run(self) -> None:
        missing = _check_dependencies()
        if missing:
            # The conversion reports missing libraries with a proper message.
            app_logger.warning("Model preparation skipped, missing libraries: {}", missing)
            self.error.emit(translator.t("errors.missing_libs", libs=", ".join(missing)))
            return

        app_logger.info(
            "Preparing models at startup (gpu={}, device={})", self.gpu_enabled, self.device_type
        )
        try:
            self._get_models()
        except DownloadCancelled:
            app_logger.info("Startup model download cancelled by the user")
            self._emit_cancelled()
            return
        except Exception as exc:
            app_logger.opt(exception=True).error("Startup model preparation failed: {}", exc)
            self.error.emit(str(exc))
            return

        if self._cancelled:
            self._emit_cancelled()
        else:
            app_logger.info("Models prepared at startup")
            self.prepared.emit()
