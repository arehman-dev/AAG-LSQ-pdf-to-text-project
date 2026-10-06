# Technical Process Documentation: End-to-End Vision OCR for Urdu & Arabic Grammar Books

**Project:** Automated High-Fidelity Text Extraction of Complex Arabic Grammar Textbooks in Urdu  
**Files Processed:**
1. `aag.pdf` (*آسان عربی گرامر* / Aasan Arabi Grammar) — **346 pages**
2. `lsq.pdf` (*لسان القرآن* / Lisan ul Quran) — **433 pages**  
**Total Volume:** 779 Pages  
**Final Result:** 100% Page Success Rate (779/779 pages extracted without loss)

---

## 1. Executive Summary & Objective

The objective was to convert two foundational Arabic grammar textbooks written in Urdu into clean, digital `.txt` format. While text extraction from standard English or printed Latin-script PDFs is trivial, these two books represent one of the most challenging document formats in digital document processing:

* **Dual-Script Typographical Complexity:** Continuous alternation between Urdu written in diagonal **Nastaliq** script and Arabic written in horizontal **Naskh** script.
* **Critical Nature of Diacritics (*Tashkeel / Harakaat*):** In Arabic grammar, vowel marks (*Zabar, Zer, Pesh, Sukun, Tanween, Shaddah, Khada Zabar*) determine grammatical state (*I'rab*). Dropping a vowel mark fundamentally destroys the meaning of grammar rules and conjugation tables (*گردان*).
* **Heterogeneous Source Documents:** One document was a digitally compiled PDF suffering from severe legacy font encoding corruption, while the other was a 100% scanned raster image document with heavy background watermarks.

This document details the diagnostic investigations, why standard tools failed, the architectural design of the custom Vision LLM pipeline, and the step-by-step execution metrics.

---

## 2. Technical Investigation: Why Traditional Methods Failed

Before implementing the vision-based solution, multiple extraction pipelines were tested directly on sample pages from both books.

### 2.1 The Case of `aag.pdf` (Digital PDF with Corrupted CMap)

* **Physical Inspection:** `aag.pdf` (10 MB, 346 pages) was authored in Microsoft Word 2010 using custom Pakistani desktop-publishing fonts: `Jameel Noori Nastaleeq`, `Rouqa Unicode`, `Alvi Nastaleeq`, and `Al_Mushaf`.
* **The Failure Mechanism:**
  When Microsoft Word compiles complex Nastaliq ligatures and Quranic diacritics into PDF, it often subsets fonts using custom 8-bit `WinAnsiEncoding` rather than standard Unicode. The resulting `ToUnicode` CMap table inside the PDF maps character codes to arbitrary glyph identifiers rather than proper Unicode code points.
* **The Empirical Result:**
  Running standard extraction (`pdftotext` / `pdfminer` / `pypdf`) resulted in severe, systematic corruption:
  
  | Expected Text (Visual Image) | Raw Digital Extraction (`pdftotext`) | Defect Description |
  | :--- | :--- | :--- |
  | **إِبْرَاهِيمُ** | `أبِ َزاٍ ٔ ِی ُه` | Vowels scattered; `ر` replaced by `ز`; letters decomposed into raw glyph tags. |
  | **مَكَّةُ** | `َم َّ‪ٜ‬ةُ` | Contains unprintable codepoints (`\u061c`, `\u065c`). |
  | **أَسْوَدُ** | `اَ ِس َو ُز` | Letter `د` replaced by `ز`. |
  | **درست** | `درس` | Final `ت` ligatures dropped entirely. |
  | **زبان** | `زناؿ` | `ب + ا` sequence mangled into `ن` and noon ghunna `ؿ`. |

**Conclusion:** Pure programmatic text extraction from `aag.pdf` was technically impossible without building a massive, heuristic-based reverse-mapping lookup table for thousands of distorted ligatures.

---

### 2.2 The Case of `lsq.pdf` (Scanned Bitmaps with Watermarks)

* **Physical Inspection:** `lsq.pdf` (182 MB, 433 pages) contained no digital text layer whatsoever. Each page was a high-resolution raster image (~350 DPI, 2550 × 3300 px).
* **The Failure Mechanism:**
  1. Every single page contains a large, low-contrast central watermark logo: `لسان القرآن`.
  2. Pages are enclosed within intricate decorative floral borders.
  3. The layout contains complex multi-directional grammar diagrams and circled numbering (`①`, `②`, `③`).
* **The Empirical Result with Tesseract OCR (v5.0, `-l urd`):**
  * Tesseract misidentified background watermark contours as active letters, injecting random punctuation strings (e.g., `6 6322603666ااھ`) into the middle of sentences.
  * Nastaliq's diagonal baseline caused Tesseract to slice words vertically, producing fragmented strings (e.g., `ط0 ام` instead of `① واحد`).
  * Arabic diacritics were stripped or mapped to English punctuation marks.
  * Reading order was frequently inverted (header sections dropped to the bottom).

---

## 3. Architecture of the Solution: Multimodal Vision OCR

To overcome both font corruption and scanned raster noise, we designed a pipeline leveraging **Multimodal Large Language Models (Gemini Vision)**. Vision LLMs evaluate the visual rendering of the page as a human reader would, completely bypassing corrupted PDF font streams and filtering out decorative visual noise.

```
                      ┌────────────────────────┐
                      │   Source PDF Files     │
                      │   (aag.pdf / lsq.pdf)  │
                      └───────────┬────────────┘
                                  │
                                  ▼
                 ┌─────────────────────────────────┐
                 │    Page Extraction (pdftoppm)   │
                 │     Rendered to 150 DPI PNG     │
                 └────────────────┬────────────────┘
                                  │
                                  ▼
                 ┌─────────────────────────────────┐
                 │   Disk Cache & Resume Guard     │
                 │   output/<book>/pages/page_XXX  │
                 └────────────────┬────────────────┘
                                  │ (Only unextracted pages)
                                  ▼
                 ┌─────────────────────────────────┐
                 │   Thread Pool (Workers: 3)      │
                 └────────┬──────────────┬─────────┘
                          │              │
                          ▼              ▼
     ┌─────────────────────────────────────────────────────────┐
     │                Vision LLM Engine (Gemini)               │
     │  - Strict scholarly prompt: Preserve Tashkeel verbatim  │
     │  - Layout Parser: Format tables into Markdown           │
     │  - Filter: Ignore central watermarks and floral frames  │
     │  - Fallback Cascade: 3.5-Flash -> 3.5-Lite -> 3.1-Lite  │
     └────────────────────────────┬────────────────────────────┘
                                  │
                                  ▼
                 ┌─────────────────────────────────┐
                 │    Per-Page Output (.txt)       │
                 └────────────────┬────────────────┘
                                  │
                                  ▼
                 ┌─────────────────────────────────┐
                 │ Master Combiner & Post-Processor│
                 │   output/<book>_extracted.txt   │
                 └─────────────────────────────────┘
```

---

## 4. Pipeline Implementation Details

The implementation is encapsulated in `ocr_vision_pipeline.py`. Key architectural decisions:

### 4.1 High-Performance Image Rendering (`pdftoppm`)
Instead of heavy Python image wrappers like `pdf2image` (which introduces `poppler` bindings and PIL memory overhead), the script invokes Linux's native `/usr/bin/pdftoppm` directly via `subprocess`.
* **Resolution:** Set to `150 DPI`. This balances crisp character detail for tiny diacritics (dots, tanween, shaddah) while keeping per-image payloads under ~600 KB.

### 4.2 Scholarly Vision Prompt Engineering
The model was guided with strict negative and positive constraints:
```python
SYSTEM_PROMPT = """You are an expert transcriber of Urdu and Arabic scholarly and educational texts.
Transcribe the content of this page image into clean, accurate, and faithful text.

STRICT INSTRUCTIONS:
1. Preserve all Urdu text in proper orthography and spelling.
2. Preserve all Arabic text with COMPLETE diacritics/tashkeel/harakaat (زبر، زیر، پیش، شد، سکون، دو زبر، دو زیر، دو پیش، کھڑا زبر). Do NOT drop or alter any vowel marks.
3. Tables: Format all tables, paradigms (گردان), and vocabulary lists using Markdown tables (| Header | ... |).
4. Ignore decorative elements: Do NOT transcribe page border decorations or background central watermarks (e.g., "لسان القرآن" watermark logos).
5. Formatting: Use clean Markdown headers (##, ###) for chapter titles, section headings, and lesson numbers.
6. Numbered lists & notes: Retain list numbering (1:, 1.1, (i), ①, etc.) and footnotes as presented.
7. Output ONLY the transcribed text. Do not include introductory notes, commentary, or markdown conversational wrappers.
"""
```

### 4.3 Model Cascading & Fault Tolerance
To prevent failures from temporary Google Cloud traffic spikes (HTTP 503 / 429), the script implements an automatic failover cascade:
1. `gemini-3.5-flash` (Primary — highest reasoning and OCR quality)
2. `gemini-3.5-flash-lite` (Secondary — high throughput fallback)
3. `gemini-3.1-flash-lite` (Tertiary fallback)
4. `gemini-3-flash-preview` (Quaternary fallback)
Each call retries up to 5 times with exponential backoff (`time.sleep(2 * attempt)`).

### 4.4 Multi-Threaded Concurrency & Smart Caching
* **Worker Threads:** Configured to `3` workers. This maximized throughput while respecting API rate limits (15 requests per minute on standard tiers).
* **Caching:** Pages are saved immediately to `output/<book>/pages/page_XXX.txt`. If the process is halted or interrupted, re-running checks for file presence and skips completed pages in 0.001s.

---

## 5. Execution Metrics & Verification Results

### 5.1 Volume & Performance Summary

| Metric | آسان عربی گرامر (`aag.pdf`) | لسان القرآن (`lsq.pdf`) | Total |
| :--- | :---: | :---: | :---: |
| **Total Pages** | 346 | 433 | **779 Pages** |
| **Source Type** | Corrupted Digital PDF | Scanned Bitmaps (350 DPI) | — |
| **Success Rate** | 100% (346 / 346) | 100% (433 / 433) | **100% (779 / 779)** |
| **Failures / Skips** | 0 | 0 | **0** |
| **Combined File Size** | 2,316,879 bytes (~2.3 MB) | 722,017 bytes (~706 KB) | **~3.0 MB** |
| **Total Extracted Lines**| 8,916 lines | 11,856 lines | **20,772 lines** |

---

### 5.2 Quality Benchmark Comparison

#### Example 1: Case Declension Table (Page 18 of `aag.pdf`)
* **Original Image Content:** Grammar table teaching *Ghair Munsarif* nouns in Nominative (*Marfoo*), Accusative (*Mansoor*), and Genitive (*Majroor*).
* **`pdftotext` Extraction:**
  `چٌد هعسب غیس هٌصسف امساء کی گسداى هع هعاًی ... أبِ َزاٍ ٔ ِی ُه ... َم َّ‪ٜ‬ةُ`
* **Vision Pipeline Output:**
  ```markdown
  ### چند معرب غیر منصرف اسماء کی گردان مع معانی

  | حالتِ رفع | معنی | حالتِ نصب | حالتِ جر |
  | :---: | :---: | :---: | :---: |
  | إِبْرَاهِيْمُ | مرد کا نام | إِبْرَاهِيْمَ | إِبْرَاهِيْمَ |
  | مَكَّةُ | شہر کا نام | مَكَّةَ | مَكَّةَ |
  | مَرْيَمُ | عورت کا نام | مَرْيَمَ | مَرْيَمَ |
  | إِسْرَائِيْلُ | حضرت یعقوبؑ کا لقب | إِسْرَائِيْلَ | إِسْرَائِيْلَ |
  | أَحْمَرُ | سرخ | أَحْمَرَ | أَحْمَرَ |
  | أَسْوَدُ | سیاہ | أَسْوَدَ | أَسْوَدَ |
  ```

#### Example 2: Watermarked Dual-Noun Rule (Page 30 of `lsq.pdf`)
* **Original Image Content:** Urdu rule with circled bullets `①`, `②` over a dense floral logo watermark.
* **Tesseract Output:**
  `Detected 187 diacritics ... 0ا2 ج2 ا ... ط0 ام :۔ ایک کے لیے ... 6 6322603666ااھ ...`
* **Vision Pipeline Output:**
  ```markdown
  # عَدَد

  اردو اور انگریزی میں عدد کے اعتبار سے اسم دو طرح کا ہوتا ہے۔ ایک کے لیے ”وَاحِد“ اور دو یا دو سے زیادہ کے لیے ”جَمْع“، لیکن عربی میں واحد اور جمع کے علاوہ دو کے لیے ایک الگ سے عدد بنایا گیا ہے جسے ”مُثَنًّى“ کہتے ہیں۔

  ① وَاحِدٌ :- ایک کے لیے
  ② مُثَنًّى :- دو کے لیے
  ③ جَمْع :- دو سے زیادہ کے لیے

  ## مُثَنًّى بنانے کا طریقہ:
  مذکر یا مؤنث دونوں طرح کے اسماء سے مُثَنًّى بنانے کے لیے واحد اسم کے آخری حرف کو
  ① فَتْحَة یعنی زَبَر دے کر
  ② اَلِف اور زِیر (کَسْرَہ) والی نُون کا اضافہ کر دیا جاتا ہے۔
  جس سے اسم کے آخر میں ”آنِ“ کی آواز پیدا ہوتی ہے، مثلاً:

  رَجُلٌ سے رَجُلَانِ 
  اِمْرَأَةٌ سے اِمْرَأَتَانِ
  صَالِحٌ سے صَالِحَانِ 
  كِتَابٌ سے كِتَابَانِ
  ```

---

## 6. Project Artifacts & Directory Structure

All scripts, outputs, and configuration files are located under `/home/arehman/00-code/aag-ocr-project/`:

```
aag-ocr-project/
├── ocr_vision_pipeline.py          # Complete multi-worker OCR pipeline CLI
├── README.md                      # Operational guide and summary
├── PROCESS_DOCUMENTATION.md       # This comprehensive process and technical audit document
├── .env                           # GEMINI_API_KEY credential storage (git-ignored)
├── .gitignore                     # Git ignore rules protecting keys and cache files
├── aag.pdf                        # Source PDF: آسان عربی گرامر (346 pages)
├── lsq.pdf                        # Source PDF: لسان القرآن (433 pages)
└── output/
    ├── aag/
    │   ├── aag_extracted.txt      # Combined full text of آسان عربی گرامر (2.3 MB)
    │   └── pages/                 # Individual page text files (page_001.txt - page_346.txt)
    └── lsq/
        ├── lsq_extracted.txt      # Combined full text of لسان القرآن (706 KB)
        └── pages/                 # Individual page text files (page_001.txt - page_433.txt)
```

---

## 7. Operational Recommendations for Future Documents

1. **For Mixed Nastaliq + Vocalized Arabic Text:** Avoid traditional character-segmentation OCR (Tesseract / EasyOCR). Always prefer Multimodal Vision models that treat page regions holistically.
2. **Resolution Tuning:** 150 DPI is the empirical sweet spot for Arabic diacritic recognition. Increasing to 300 DPI doubles payload transmission time without meaningful accuracy gains.
3. **API Rate Limiting:** When processing books over 300 pages on standard API tiers, maintain 2 to 3 worker threads with a 1-second delay between batch launches to prevent persistent HTTP 429 backpressure.
