#  Scanbridge

** Note on Project Status: The features and architecture described below represent the full roadmap and will be implemented in the later stages of the application. In the current MVP (Minimum Viable Product), the system functions by taking a PDF input and generating structured HTML output.**
> **A rights-based, privacy-first, decentralized, and AI-powered accessible document transformation platform for blind and visually impaired individuals.**

---

##  The Manifesto: Why Scanbridge?

Today, the vast majority of digital documents and scanned books remain trapped behind insurmountable barriers for blind and visually impaired individuals. [cite_start]Traditional OCR (Optical Character Recognition) tools treat pages merely as a flat pool of raw text[cite: 4]. In doing so:
* **Heading hierarchies are completely destroyed**, paralyzing the structural navigation capabilities of screen readers.
* **Two-column academic papers or complex layouts** are read straight across from left to right, turning structured literature into a confusing word soup.
* **Tables and diagrams** lose their contextual relationships, rendering data entirely meaningless.
* A 300-page printed document often balloons into a chaotic, unnavigable **600-page cognitive mess (resembling Braille text swelling)** due to the complete lack of semantic formatting.

To make matters worse, existing AI solutions that promise to fix these issues are either proprietary and prohibitively expensive, or they blatantly violate user privacy by uploading sensitive materials unencrypted to data-harvesting corporate clouds.

**Scanbridge is a rebellion against this status quo.** We believe that access to information is not a privilege or a luxury—it is a fundamental human right. Our mission is to empower a student with even the lowest-spec computer to harness the power of decentralized community servers (Fediverse) to transform unreadable documents into pristine, highly structured, and semantic HTML5 or EPUB3 files, without ever compromising their data privacy.

---

## 🏗️ Architecture & Core Technical Innovations

Scanbridge solves the structural hierarchy and layout crisis through **Server-Side Cross-Referencing** and a dynamic, **LiteLLM-powered** discovery network.



### 1. Hybrid Processing & Model Liberty (Client-Side Discovery)
Unlike rigid platforms that force users into a single AI model, Scanbridge respects both user preference and server ownership:
* **Server Autonomy (The Menu Protocol):** Every voluntary node provider in the Fediverse defines their own available hardware and local models (e.g., *DeepSeek-R1*, *Qwen2-VL*, or *Gemma-2*). Nodes broadcast their current capabilities via a lightweight `/info` metadata endpoint.
* **Dynamic Matching (Service Discovery):** The client application dynamically fetches available nodes. Users can choose a node based on its trust level or filter the entire network by the specific "brain" they need for their current task (e.g., selecting an advanced Vision-Language Model like *Qwen2-VL* for complex tables, or a reasoning model like *DeepSeek-R1* for heavy academic logic).

### 2. Privacy via Input Chunking & Transient State
* **On-Device Initial Pass:** Basic text layer anchoring is done locally using efficient Python libraries (`EasyOCR` and `Pix2Text`).
* **Distributed Processing:** To prevent data leaks, documents are sliced into page-by-page chunks on the client side and distributed across different nodes. A rogue node can never intercept the entire book.
* **Zero-Retention Processing:** Using asymmetric hybrid cryptography (AES-GCM-256 + RSA), data is transferred securely. Worker nodes decrypt the chunk **exclusively in-memory (RAM)** via a unified LiteLLM Proxy. Once the contextual alt-text or semantic table layout is generated and returned to the client, the memory is instantly wiped.

### 3. Rich ZIP / Web Bundle Delivery
The server bundles the processed sections, geometric assets, and contextual image descriptions into a structured, lightweight ZIP file containing organized HTML5 and metadata. The client unzips this bundle locally and uses native engines to assemble it instantly into an accessible **EPUB3** or editable **ODT** format.

---

##  Clean Tech Stack (No Dependency Hell)
Scanbridge deliberately avoids system-level software dependencies (like heavy external binaries or traditional C++ OCR frameworks) to ensure effortless deployments across all operating systems:
* **Image Preprocessing:** `OpenCV` (grayscale conversion, bilateral filtering, Otsu's thresholding, and non-local means denoising to improve OCR accuracy).

* **Layout & Local Text Processing:** `PyMuPDF` (lightweight PDF parsing), `easyocr` (pure-Python deep learning OCR), `pix2text` (mathematical formula & LaTeX recognition).
* **AI Orchestration & API Layer:** `FastAPI` (node endpoints), `litellm` (universal LLM/VLM wrapper and dynamic model routing).
* **Semantic Formatting:** `beautifulsoup4` (valid HTML5 tag enforcement), `pypandoc` (instant local EPUB3/ODT compilation).
* **Security:** `cryptography` (secure asymmetric key exchange and token validation).

---

##  Scientific Grounding & Literature Validation
[cite_start]The Scanbridge architecture directly addresses the major systemic crises highlighted in recent assistive technology (AT) literature[cite: 1, 142]:
1. [cite_start]**The Researcher-User Disconnect (82% Gap):** Academic literature shows that **82%** of AT research fails to include blind and low-vision (BLV) individuals in design phases, focusing on "technically interesting" problems rather than actual user priorities[cite: 146, 148, 152]. [cite_start]Scanbridge is built on **participatory co-design principles**, prioritizing structural document layout, semantic headers, and proper table tagging—the exact high-priority tasks users actually demand[cite: 150, 154, 156].
2. [cite_start]**The Cloud vs. Offline Dilemma:** Studies emphasize the tradeoff between the high accuracy of cloud giants (inducing privacy risks and internet dependency) and the strict performance limits of offline devices[cite: 30, 31, 33, 39]. Our dynamic Fediverse model bypasses this friction by using encrypted, zero-retention server islands.
3. [cite_start]**The Empirical Model Core:** Experiments confirm that ResNet-backed CNN-LSTM deep learning frameworks deliver the highest text/image-captioning accuracy (**83%**) under non-laboratory conditions[cite: 67, 70]. Scanbridge relies natively on these highly robust, optimized model backbones via its Python core.

---

##  License

This project is licensed under the **GNU General Public License v3 (GPLv3)**. 

This guarantees that the software is completely free, open-source, and will remain so. Any derivative works or sub-projects utilizing the Scanbridge codebase are legally bound to also open their source code under the same copyleft principles. Knowledge must be shared freely to truly liberate.

---

