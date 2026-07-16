"""
main.pyw

Application entry point for Scanbridge.

The .pyw extension prevents Windows from opening a console window.
All stdout / stderr output is captured by the logger pipeline and
written to the daily log file inside logs/.

Import order matters:
1. logger  — must be first to redirect stdout/stderr before any other output.
2. i18n    — initialise the Translator (loads the saved or detected language).
3. Qt app  — then build the UI with the active translations in place.
"""

import sys

import logger  # Activates the stdout/stderr pipeline immediately
from utils.i18n import translator  # Initialise translations before the UI
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from engine.ocr_worker import OCRWorker


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Scanbridge")

    window = MainWindow(OCRWorker)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
