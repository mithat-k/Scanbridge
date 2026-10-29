# Graph Report - scanbridge  (2026-10-29)

## Corpus Check
- Corpus is ~8,942 words - fits in a single context window. You may not need a graph.

## Summary
- 215 nodes · 365 edges · 9 communities (5 shown, 4 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 26 edges (avg confidence: 0.79)
- Token cost: 55,099 input · 0 output

## Community Hubs (Navigation)
- i18n & Settings Persistence
- Vision, Privacy & Tech Stack
- OCR Conversion Pipeline
- Main Window UI
- Health Check & Accessibility
- Logging Infrastructure
- Settings Dialog

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 26 edges
2. `OCRWorker` - 20 edges
3. `RULES.MD - Scanbridge AI Rulebook (Constitution)` - 15 edges
4. `SettingsDialog` - 12 edges
5. `readme.md - Scanbridge README` - 12 edges
6. `Clean Tech Stack (portable, Python-first)` - 11 edges
7. `requirements.txt - Python dependencies` - 10 edges
8. `_announce()` - 9 edges
9. `_load_settings()` - 9 edges
10. `_Translator` - 8 edges

## Surprising Connections (you probably didn't know these)
- `MainWindow` --uses--> `HealthCheckerWorker`  [INFERRED]
  ui/main_window.py → engine/health_checker.py
- `main()` --uses--> `OCRWorker`  [INFERRED]
  main.py → engine/ocr_worker.py
- `MainWindow` --uses--> `OCRWorker`  [INFERRED]
  ui/main_window.py → engine/ocr_worker.py
- `SettingsDialog` --uses--> `OCRWorker`  [INFERRED]
  ui/settings_dialog.py → engine/ocr_worker.py
- `main()` --calls--> `MainWindow`  [EXTRACTED]
  main.py → ui/main_window.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Code protection rules (ASLA YAPMA)** — rule_1_no_easyocr_workers_param, rule_2_pix2text_file_path_not_pil, rule_3_pix2text_page_elements, rule_4_no_finished_signal_use_result_ready, rule_5_filter_garbage_and_watermarks, rule_6_aria_hidden_inactive_pages, rule_no_system_dependencies_cross_platform [EXTRACTED]
- **Accessibility (A11Y) standards** — rule_focus_policy_strong_focus, rule_screen_reader_qaccessible_no_win32, rule_html_to_html_mathml_strategy, rule_pandoc_mathml_integration [EXTRACTED]
- **Privacy-preserving distributed architecture** — input_chunking_transient_processing, aes_gcm_rsa_encryption, local_ocr_anchoring, fediverse_decentralized_nodes, privacy_philosophy [INFERRED]

## Communities (9 total, 4 thin omitted)

### Community 0 - "i18n & Settings Persistence"
Cohesion: 0.07
Nodes (12): _load_locale(), _Translator, _detect_os_language(), _ensure_logs_dir(), get_language(), get_ocr_languages(), get_settings_path(), is_manual_set() (+4 more)

### Community 1 - "Vision, Privacy & Tech Stack"
Cohesion: 0.08
Nodes (43): AES-GCM-256 encryption with RSA key exchange, BeautifulSoup4, Clean Tech Stack (portable, Python-first), cryptography (RSA + AES), Design Philosophy (four principles), Dynamic Service Discovery (trust, hardware, proximity, models), EasyOCR, EPUB3 / ODT export (+35 more)

### Community 2 - "OCR Conversion Pipeline"
Cohesion: 0.07
Nodes (9): _build_html_template(), _check_dependencies(), _clean_image_opencv(), _denoise(), _is_meaningless(), _normalize_text(), OCRWorker, _pil_to_numpy() (+1 more)

### Community 4 - "Health Check & Accessibility"
Cohesion: 0.14
Nodes (8): check_system_health(), HealthCheckerWorker, PyQt6, QAccessible / QAccessibleEvent (Alert, NameChanged), Rule 4: no 'finished' signal in HealthCheckerWorker; use result_ready, StrongFocus only on interactive QPushButtons, not QLabel/QProgressBar, Screen reader announcements via QAccessible; Win32 ctypes forbidden, Tech stack: PyQt6 (Python 3.14+) with async QThread architecture

### Community 5 - "Logging Infrastructure"
Cohesion: 0.14
Nodes (4): get_log_file_path(), setup_logger(), StreamToLogger, main()

## Ambiguous Edges - Review These
- `No disk I/O during OCR: in-memory Pixmap -> PIL Image -> NumPy` → `Rule 2: pass temp file path, not PIL Image, to Pix2Text recognize_page()`  [AMBIGUOUS]
  RULES.MD · relation: constrains

## Knowledge Gaps
- **3 isolated node(s):** `FastAPI`, `Dynamic Service Discovery (trust, hardware, proximity, models)`, `GNU GPL-3.0 License`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 84 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `Main Window UI` to `OCR Conversion Pipeline`, `Health Check & Accessibility`, `Logging Infrastructure`, `Settings Dialog`?**
  _High betweenness centrality (0.241) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `MainWindow` (e.g. with `HealthCheckerWorker` and `OCRWorker`) actually correct?**
  _`MainWindow` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `FastAPI`, `Dynamic Service Discovery (trust, hardware, proximity, models)`, `GNU GPL-3.0 License` to the rest of the system?**
  _3 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `i18n & Settings Persistence` be split into smaller, more focused modules?**
  _Cohesion score 0.07171717171717172 - nodes in this community are weakly interconnected._
- **Why does `OCRWorker` connect `OCR Conversion Pipeline` to `i18n & Settings Persistence`, `Main Window UI`, `Health Check & Accessibility`, `Logging Infrastructure`, `Settings Dialog`?**
  _High betweenness centrality (0.196) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `OCRWorker` (e.g. with `main()` and `MainWindow`) actually correct?**
  _`OCRWorker` has 3 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `No disk I/O during OCR: in-memory Pixmap -> PIL Image -> NumPy` and `Rule 2: pass temp file path, not PIL Image, to Pix2Text recognize_page()`?**
  _Edge tagged AMBIGUOUS (relation: constrains) - confidence is low._