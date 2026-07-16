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
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from logger import app_logger
from utils.i18n import translator

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Regex for detecting real LaTeX / formula symbols — avoids false positives.
_MATH_RE = re.compile(r"[=\^_\\{}]|\$|\bfrac\b|\bsqrt\b|\bsum\b|\bint\b")


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

    # Strip alpha channel
    if pix.alpha:
        pix_no_alpha = fitz.Pixmap(fitz.csRGB, pix, 0)  # 0 = drop alpha
        pix = pix_no_alpha

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
    progress : (int, str)  – percentage [0–100] and a status message
    finished : str         – absolute path to the output HTML file
    error    : str         – error message
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    # Class-level model cache (RULES.MD: models are kept alive for the session)
    _reader      = None
    _p2t         = None
    _reader_gpu  = None
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
            self._process()
            app_logger.info(translator.t("log.ocr_done"))
        except Exception as exc:
            app_logger.error(translator.t("log.ocr_error", error=str(exc)), exc_info=True)
            self.error.emit(str(exc))

    def _process(self) -> None:
        self.progress.emit(5, translator.t("progress.checking_libs"))

        missing = _check_dependencies()
        if missing:
            libs = ", ".join(missing)
            self.error.emit(translator.t("errors.missing_libs", libs=libs))
            return

        import fitz
        from bs4 import BeautifulSoup
        import pypandoc

        self.progress.emit(8, translator.t("progress.preparing_models"))
        reader, p2t = self._get_models()

        self.progress.emit(10, translator.t("progress.opening_pdf"))

        doc = fitz.open(self.pdf_path)
        try:
            total = len(doc)

            if total == 0:
                self.error.emit(translator.t("errors.empty_pdf"))
                return

            # ── Phase 1: Watermark and repeated-text detection ──
            self.progress.emit(12, translator.t("progress.phase1"))
            raw_page_results = []
            normalized_counts: dict[str, int] = {}

            for i, page in enumerate(doc):
                if self._cancelled:
                    self.error.emit(translator.t("errors.cancelled"))
                    return

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
                    if norm:
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
                    self.error.emit(translator.t("errors.cancelled"))
                    return

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

        self.progress.emit(85, translator.t("progress.building_html"))
        html_content = soup.prettify()

        # Pandoc MathML integration
        self.progress.emit(95, translator.t("progress.pandoc_compile"))
        try:
            final_html = pypandoc.convert_text(
                html_content,
                to="html",
                format="html",
                extra_args=["--mathml"],
            )
        except Exception:
            # If Pandoc fails, preserve the original content
            final_html = html_content

        # Final disk write — only the output file (no intermediate disk I/O)
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(final_html)

        self.progress.emit(100, translator.t("progress.done"))
        self.finished.emit(self.output_path)

    # ------------------------------------------------------------------
    # Model loading (with session-level cache)
    # ------------------------------------------------------------------

    def _get_models(self):
        """Load and cache EasyOCR and Pix2Text models. Re-initialises only on device change."""
        import easyocr

        # EasyOCR — re-initialise if GPU preference changed
        # RULES.MD rule 1: never pass `workers` to easyocr.Reader
        if (
            OCRWorker._reader is None
            or OCRWorker._reader_gpu != self.gpu_enabled
        ):
            key = "loading.easyocr_gpu" if self.gpu_enabled else "loading.easyocr_cpu"
            self.progress.emit(10, translator.t(key))
            OCRWorker._reader = easyocr.Reader(
                ["tr", "en"],
                gpu=self.gpu_enabled,
                quantize=(not self.gpu_enabled),  # INT8 quantisation on CPU
            )
            OCRWorker._reader_gpu = self.gpu_enabled

        # Pix2Text — re-initialise if device changed
        if (
            OCRWorker._p2t is None
            or OCRWorker._p2t_device != self.device_type
        ):
            self.progress.emit(14, translator.t("loading.pix2text"))
            OCRWorker._p2t = self._load_pix2text(self.device_type)
            OCRWorker._p2t_device = self.device_type

        return OCRWorker._reader, OCRWorker._p2t

    @staticmethod
    def _load_pix2text(device: str):
        """
        Load Pix2Text with a three-level fallback strategy.

        Level 1 — Force PyTorch backend (avoids missing ONNX file errors).
        Level 2 — Disable fast mode for older Pix2Text versions.
        Level 3 — Direct constructor as last resort.
        """
        from pix2text import Pix2Text

        try:
            return Pix2Text.from_config(
                total_configs={'formula': {'model_backend': 'pytorch'}},
                device=device,
            )
        except Exception:
            pass

        try:
            return Pix2Text.from_config(device=device, use_fast=False)
        except Exception:
            pass

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
