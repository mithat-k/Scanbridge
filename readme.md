# Scanbridge

> **Project Status:** The features and architecture described below represent the long-term roadmap of Scanbridge. The current MVP (Minimum Viable Product) focuses on transforming PDF documents into structured, semantic HTML output.

> **A rights-based, privacy-first, decentralized, AI-powered accessible document transformation platform for blind and visually impaired individuals.**

---

# The Manifesto: Why Scanbridge?

Today, the vast majority of digital documents and scanned books remain trapped behind accessibility barriers for blind and visually impaired individuals. Traditional OCR systems primarily extract plain text while failing to preserve the structural semantics of a document.[^1][^2]

As a result:

- **Heading hierarchies are destroyed**, preventing efficient structural navigation with screen readers.[^1]
- **Multi-column academic papers and complex layouts** are flattened into a continuous reading order, making scientific literature difficult to understand.[^1][^2]
- **Tables, diagrams, and visual relationships** lose their contextual meaning, rendering data difficult—or impossible—to interpret.[^2]
- A printed document can expand into an unnecessarily long and cognitively exhausting reading experience because semantic formatting is completely lost.[^2]

Existing AI-based alternatives attempt to address some of these issues, yet they typically suffer from one of two major limitations:

- They are proprietary and prohibitively expensive.
- They require users to upload sensitive documents to centralized cloud infrastructure, introducing significant privacy concerns.[^3][^4]

**Scanbridge** is a response to this status quo.

We believe access to information is not a privilege—it is a fundamental human right.

Our goal is to enable anyone, even with modest hardware, to leverage decentralized community-operated servers (Fediverse) to transform inaccessible documents into highly structured HTML5 or EPUB3 files while maintaining complete ownership of their data.

---

# 🏗️ Architecture & Core Technical Innovations

Scanbridge addresses document hierarchy reconstruction and layout understanding through **Server-Side Cross-Referencing** combined with a decentralized **LiteLLM-powered** processing network.

## 1. Hybrid Processing & Model Liberty (Client-Side Discovery)

Unlike traditional AI platforms that force users into a single proprietary model, Scanbridge separates client choice from server ownership.

### Server Autonomy (Menu Protocol)

Every voluntary Fediverse node publishes its available hardware and locally hosted models (such as **DeepSeek-R1**, **Qwen2-VL**, or **Gemma-2**) through a lightweight `/info` endpoint.

### Dynamic Service Discovery

The client dynamically discovers available nodes and allows users to select providers according to:

- Trust level
- Hardware capability
- Geographic proximity
- Available AI models

For example, users may select:

- **Qwen2-VL** for complex document layout reconstruction.
- **DeepSeek-R1** for reasoning-intensive academic documents.

## 2. Privacy Through Input Chunking & Transient Processing

Rather than transmitting an entire document to a single server, Scanbridge distributes processing securely.

- Initial OCR anchoring is performed locally using **EasyOCR** and **Pix2Text**.
- Documents are divided into page-level chunks before transmission.
- Individual chunks are distributed across different worker nodes, preventing any single node from reconstructing the complete document.
- AES-GCM-256 encryption combined with RSA key exchange protects all transmitted data.
- Worker nodes decrypt pages exclusively in volatile memory (RAM), process them through LiteLLM Proxy, immediately return semantic information, and erase all temporary data afterward.

This architecture minimizes privacy risks while preserving scalability.

## 3. Rich ZIP / Web Bundle Delivery

Instead of returning a single text file, Scanbridge packages processed outputs into a lightweight archive containing:

- Structured HTML5
- Metadata
- Geometric layout information
- Contextual image descriptions

The client reconstructs the archive locally into accessible formats such as:

- EPUB3
- ODT

without requiring additional cloud processing.

---# Clean Tech Stack

Scanbridge intentionally avoids heavyweight system-level dependencies (such as native OCR engines or platform-specific binaries) in favor of a portable, Python-first architecture that can run consistently across operating systems.

| Layer | Technology | Purpose |
|--------|------------|---------|
| Image Preprocessing | OpenCV | Grayscale conversion, bilateral filtering, Otsu thresholding, denoising |
| PDF Processing | PyMuPDF | Lightweight PDF parsing |
| Local OCR | EasyOCR | Deep-learning OCR engine |
| Formula Recognition | Pix2Text | Mathematical expressions & LaTeX |
| API Layer | FastAPI | REST endpoints |
| AI Routing | LiteLLM | Universal LLM/VLM abstraction and routing |
| Semantic HTML | BeautifulSoup4 | HTML5 validation and cleanup |
| Document Export | PyPandoc | EPUB3 / ODT generation |
| Security | cryptography | RSA + AES encryption |

---

# Scientific Grounding & Literature Validation

The Scanbridge architecture is not merely a software design; it is a direct response to recurring problems identified throughout contemporary assistive technology literature.[^5][^6]

## Researcher–User Disconnect

One of the most alarming findings in recent research is that approximately **82%** of assistive technology studies do **not** involve blind or low-vision participants during system design.[^7]

As a consequence, researchers frequently optimize technically interesting tasks rather than solving the real-world accessibility problems users prioritize.

Scanbridge adopts **participatory co-design principles**, emphasizing:

- semantic document structure
- heading reconstruction
- accessible tables
- navigable reading order

because these consistently appear among users' highest priorities.[^7][^8]

---

## Privacy vs. Cloud Computing

Current literature identifies an ongoing trade-off between:

- high-accuracy cloud AI services,
- and privacy-preserving offline systems.[^3][^9][^10]

Cloud platforms provide stronger computational resources but introduce:

- privacy concerns,
- internet dependency,
- latency,
- recurring infrastructure costs.

Scanbridge approaches this problem differently.

Instead of choosing exclusively between cloud and offline processing, it distributes encrypted page-level workloads across independent community servers while maintaining zero-retention processing.

---

## Empirical AI Foundations

Multiple experimental studies demonstrate that modern CNN-LSTM architectures—particularly those using **ResNet** feature extraction—achieve state-of-the-art performance for OCR and contextual image understanding in realistic environments.[^11][^12][^13]

Rather than developing proprietary neural architectures, Scanbridge leverages these validated model families through an interchangeable LiteLLM backend, enabling rapid adoption of future open-source multimodal models.

---

# Why HTML Instead of Plain Text?

Accessibility is not simply about extracting characters.

Screen readers rely heavily on semantic structure.

A correctly tagged HTML document allows users to navigate by:

- headings,
- landmarks,
- lists,
- tables,
- figures,
- captions,

instead of reading an entire document sequentially.

Scanbridge therefore reconstructs semantic HTML before exporting EPUB3 or ODT.

The semantic document becomes the canonical representation—not plain OCR text.

---

# Privacy Philosophy

Privacy is treated as a system property rather than an optional feature.

Every architectural decision follows several principles:

- local preprocessing whenever possible;
- encrypted communication;
- distributed page processing;
- transient in-memory computation;
- zero persistent storage on worker nodes.

This allows sensitive academic, governmental, legal, or medical documents to be processed without permanently exposing their contents to centralized infrastructure.

---

# Design Philosophy

Scanbridge is built around four principles:

1. Accessibility is a human right.
2. Users should own their documents.
3. AI should remain replaceable rather than monopolized.
4. Communities should be able to operate accessible infrastructure independently.

These principles guide every architectural decision throughout the project.

---# License

Scanbridge is released under the **GNU General Public License v3.0 (GPL-3.0)**.

This guarantees that:

- everyone is free to use the software,
- everyone may study and modify the source code,
- derivative works must remain open-source under the same license,
- improvements made by the community continue benefiting future users.

Knowledge should remain accessible—just like information itself.

---

# Roadmap

## Phase 1 — MVP ✅

- PDF upload
- OCR preprocessing
- Semantic HTML generation
- Basic document reconstruction

## Phase 2

- Semantic heading reconstruction
- Table understanding
- Figure caption generation
- EPUB3 export
- ODT export

## Phase 3

- Distributed Fediverse node discovery
- LiteLLM Proxy integration
- Multi-model routing
- Zero-retention worker nodes

## Phase 4

- Collaborative community nodes
- Reputation & trust scoring
- Intelligent workload balancing
- Cross-reference semantic reconstruction
- Advanced multimodal document understanding

---

# Contributing

Contributions are welcome.

Whether you are interested in:

- accessibility,
- OCR,
- computer vision,
- multimodal AI,
- distributed systems,
- privacy engineering,
- assistive technologies,

your contributions are appreciated.

Before opening large pull requests, please open an issue describing the proposed improvement.

---

# References

[^1]: American Foundation for the Blind. *Optical Character Recognition Systems*. https://afb.org/node/16207/optical-character-recognition-systems

[^2]: Mathur, S., & Pathare, P. *AI based Reading System for Blind using OCR*. Semantic Scholar. https://www.semanticscholar.org/paper/AI-based-Reading-System-for-Blind-using-OCR-Mathur-Pathare/5488c02e60b203f1d54ea98e8ed63ad3bd3ffcbd

[^3]: *Accessibility Evaluation of Major Assistive Mobile Applications Available for the Visually Impaired*. ResearchGate. https://www.researchgate.net/publication/376361274_Accessibility_evaluation_of_major_assistive_mobile_applications_available_for_the_visually_impaired

[^4]: *Evaluation and Comparison of Artificial Intelligence Vision Aids: OrCam MyEye 1 and Seeing AI*. ResearchGate. https://www.researchgate.net/publication/353519592_Evaluation_and_Comparison_of_Artificial_Intelligence_Vision_Aids_Orcam_MyEye_1_and_Seeing_AI

[^5]: *Artificial Intelligence Solutions for the Visually Impaired: A Review*. ResearchGate. https://www.researchgate.net/publication/369880173_Artificial_Intelligence_Solutions_for_the_Visually_Impaired_A_Review

[^6]: *Beyond Access: Rethinking Assistive Technology for Individuals with Visual Impairments in Türkiye*. Taylor & Francis. https://www.tandfonline.com/doi/full/10.1080/17483107.2025.2560092

[^7]: Gamage, B., et al. *What Do Blind and Low-Vision People Really Want from Assistive Smart Devices? Comparison of the Literature with a Focus Study*. arXiv. https://arxiv.org/abs/2505.19325

[^8]: Gamage, B., et al. *What Do Blind and Low-Vision People Really Want from Assistive Smart Devices?* ASSETS. https://bhanukagamage.com/assets/papers/ASSETS2023.pdf

[^9]: *Development of a Fully Autonomous Offline Assistive System*. PMC. https://pmc.ncbi.nlm.nih.gov/articles/PMC12526525/

[^10]: *Accessibility Evaluation of Major Assistive Mobile Applications Available for the Visually Impaired*. ResearchGate. https://www.researchgate.net/publication/376361274_Accessibility_evaluation_of_major_assistive_mobile_applications_available_for_the_visually_impaired

[^11]: *Deep-Learning-Based Cognitive Assistance Embedded Systems*. MDPI Applied Sciences. https://www.mdpi.com/2076-3417/15/11/5887

[^12]: *Deep Learning Reader for Visually Impaired*. MDPI Electronics. https://www.mdpi.com/2079-9292/11/20/3335

[^13]: *Deep Learning and Particle Swarm Optimisation-Based Techniques*. PMC. https://pmc.ncbi.nlm.nih.gov/articles/PMC8553597/

---

## Citation

If you use Scanbridge in academic work, presentations, or research, please cite the repository.

```bibtex
@software{scanbridge,
  title={Scanbridge: Privacy-First Decentralized Semantic OCR for Accessible Documents},
  author={mithat-k},
  year={2026},
  license={GPL-3.0},
  url={https://github.com/mithat-k/Scanbridge}
}
```