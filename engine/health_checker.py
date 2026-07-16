"""
engine/health_checker.py

Inspects system hardware asynchronously and reports the result via Qt signals.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from logger import app_logger
from utils.i18n import translator


# ---------------------------------------------------------------------------
# Standalone helper — can also be called outside the worker thread
# ---------------------------------------------------------------------------

def check_system_health() -> dict:
    """
    Check for a CUDA-capable GPU and its memory capacity.

    Falls back to CPU mode silently if torch is not installed or a DLL
    error occurs (e.g. WinError 1114 on Windows).

    Returns a dict with the following keys:
        gpu_available  (bool)
        gpu_name       (str)
        device_type    (str)  – 'cuda' | 'cpu'
        vram_gb        (float)
        announcement   (str)  – localized status message
        recommendation (str)  – 'GPU' | 'CPU'
    """
    app_logger.info(translator.t("health.scanning"))

    result: dict = {
        "gpu_available": False,
        "gpu_name": "—",
        "device_type": "cpu",
        "vram_gb": 0.0,
        "announcement": translator.t("status.gpu_not_found"),
        "recommendation": "CPU",
    }

    try:
        import torch
    except (ImportError, OSError):
        # torch not installed or DLL error
        result["announcement"] = translator.t("status.pytorch_failed")
        result["recommendation"] = "CPU"
        app_logger.info(translator.t("health.result", announcement=result["announcement"]))
        return result

    try:
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram_gb = round(props.total_memory / (1024 ** 3), 1)

            result.update(
                {
                    "gpu_available": True,
                    "gpu_name": name,
                    "device_type": "cuda",
                    "vram_gb": vram_gb,
                    "announcement": translator.t("status.gpu_found"),
                    "recommendation": "GPU",
                }
            )
    except Exception:
        # CUDA query failed — continue with CPU
        pass

    app_logger.info(translator.t("health.result", announcement=result["announcement"]))
    return result


# ---------------------------------------------------------------------------
# Background worker thread
# ---------------------------------------------------------------------------

class HealthCheckerWorker(QThread):
    """
    Runs the system health check in a background thread so the UI stays
    responsive during startup.

    Signals
    -------
    loading      : str  – "Scanning system…" etc.
    result_ready : dict – check_system_health() output

    Note: The signal is named 'result_ready' (not 'finished') to avoid
    shadowing QThread's own lifecycle signal, which would cause a deadlock.
    (See RULES.MD rule 4.)
    """

    loading = pyqtSignal(str)
    result_ready = pyqtSignal(dict)

    def run(self) -> None:
        self.loading.emit(translator.t("status.scanning_system"))
        result = check_system_health()
        self.result_ready.emit(result)
