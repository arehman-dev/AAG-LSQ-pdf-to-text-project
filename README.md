# Arabic & Urdu Grammar Books OCR Pipeline

Automated high-fidelity transcription pipeline for Arabic grammar textbooks written in Urdu:
1. **آسان عربی گرامر** (*Aasan Arabi Grammar*) — 346 pages
2. **لسان القرآن** (*Lisan ul Quran*) — 433 pages

---

## 1. The Challenge & Workaround

Traditional extraction tools and standard OCR fail on these books due to:
* **Font CMap Corruption (`aag.pdf`)**: Uses legacy Pakistani Nastaliq/Quranic fonts (`Jameel Noori`, `Alvi`, `Rouqa`). Direct text extractors (`pdftotext`) produce garbled letters (`د` $\rightarrow$ `ز`) and destroyed Arabic vocalization (*Tashkeel*).
* **Scanned Watermarked Pages (`lsq.pdf`)**: 100% raster scans with a heavy central logo watermark and decorative margins that break traditional OCR engines like Tesseract.

### The Solution
A **Multimodal Vision LLM pipeline** (`gemini-3.5-flash` with automatic fallback to `gemini-3.5-flash-lite`).
* **100% Arabic Diacritics**: Retains all *Zabar, Zer, Pesh, Sukun, Tanween, Shaddah*.
* **Urdu Orthography**: Verbatim transcription of Nastaliq text without ligature confusion.
* **Layout Awareness**: Automatically structures tables (*گردان*, vocabulary lists) into Markdown tables.
* **Noise Suppression**: Ignores decorative page borders and central watermarks.

---

## 2. Dependencies & Requirements

* **System Tools**: `poppler-utils` (`pdftoppm` for high-resolution page rendering).
* **Python**: Standard Python 3 with `requests` (no heavy ML packages or SDKs needed).
* **Configuration**: Gemini API key stored in `.env`.

```bash
# Required environment variable (or put in .env)
GEMINI_API_KEY="your_api_key_here"
```

---

## 3. Directory Layout

```
aag-ocr-project/
├── ocr_vision_pipeline.py          # Multithreaded Vision OCR CLI
├── .env                           # API credentials (git-ignored)
├── .gitignore                     # Ignores .env and large caches
├── aag.pdf                        # Source PDF (346 pages)
├── lsq.pdf                        # Source PDF (433 pages)
└── output/
    ├── aag/
    │   ├── aag_extracted.txt      # Complete book text (2.3 MB)
    │   └── pages/                 # Individual page text files (001–346)
    └── lsq/
        ├── lsq_extracted.txt      # Complete book text (706 KB)
        └── pages/                 # Individual page text files (001–433)
```

---

## 4. Usage

Run the pipeline using the command line:

```bash
# Convert a specific page range with 3 concurrent workers
./ocr_vision_pipeline.py -f aag.pdf -p 1-10 -w 3

# Convert all pages of a book
./ocr_vision_pipeline.py -f lsq.pdf -p all -w 3
```

### Key Script Features:
* **`-w / --workers`**: Concurrent thread pool for faster page throughput.
* **Automatic Resume**: Skips existing pages in `output/<book>/pages/` to prevent duplicate API calls.
* **Auto-Combine**: Assembles individual page text files into a single master `.txt` file upon completion.
