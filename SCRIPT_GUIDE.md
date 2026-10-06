# Script Documentation: `ocr_vision_pipeline.py`

A lightweight, standalone CLI tool for extracting complex, multi-lingual educational texts (specifically Urdu Nastaliq and Arabic with full *Tashkeel*) from PDF documents using Multimodal Vision LLMs.

---

## 1. Prerequisites & Dependencies

The script relies solely on standard Linux utilities and Python's built-in networking library:

| Dependency | Type | Purpose | Installation |
| :--- | :--- | :--- | :--- |
| **Python 3.8+** | Runtime | Script execution | Pre-installed |
| **`requests`** | Python Lib | Direct HTTP REST calls to Vision APIs | `pip install requests` |
| **`pdftoppm`** | System Tool | Ultra-fast PDF page-to-PNG rendering | `sudo apt install poppler-utils` |
| **Gemini API Key** | Credential | Model authentication | Put `GEMINI_API_KEY="xxx"` in `.env` |

*No heavy frameworks (PyTorch, TensorFlow, OpenCV, or Hugging Face) are required.*

---

## 2. Command-Line Reference

```bash
./ocr_vision_pipeline.py -f <PDF_FILE> [OPTIONS]
```

### Options:

| Flag | Argument | Default | Description |
| :--- | :--- | :--- | :--- |
| **`-f`, `--file`** | `PATH` | *Required* | Path to input PDF file (e.g. `aag.pdf` or `lsq.pdf`). |
| **`-p`, `--pages`** | `RANGE` | `1-5` | Pages to process: single (`18`), range (`1-10`), list (`1,3,5`), or `all`. |
| **`-w`, `--workers`** | `INT` | `2` | Number of concurrent threads for parallel page processing. |
| **`--provider`** | `gemini\|openai` | `gemini` | Vision LLM API provider. |
| **`--model`** | `NAME` | `gemini-3.5-flash` | Specific model to use. Automatically cascades to fallbacks on 503/429. |
| **`--api-key`** | `KEY` | *None* | Explicit API key (defaults to `.env` or `GEMINI_API_KEY` env var). |
| **`-o`, `--output-dir`** | `PATH` | `output` | Directory where images, page texts, and combined texts are stored. |
| **`--dpi`** | `INT` | `150` | Resolution for extracted page images (150 DPI is optimal for Tashkeel). |
| **`--delay`** | `FLOAT` | `1.0` | Pause in seconds between API requests per worker to manage rate limits. |
| **`--no-combine`** | Flag | `False` | Disables merging individual page files into a final combined book text. |

---

## 3. Architecture & Functional Components

The script consists of 8 modular functions:

```
load_dotenv() ──► parse_page_range() ──► extract_page_image() ──► ocr_gemini() / ocr_openai()
                                                                          │
                                                                   process_single_page()
                                                                          │
                                                                 ThreadPoolExecutor
                                                                          │
                                                                Combine into Master .txt
```

### Core Functions:
1. **`load_dotenv()`**:
   * Scans for a `.env` file in current and parent directories and exports key-value pairs without requiring the `python-dotenv` package.
2. **`extract_page_image(pdf_path, page_num, output_img_path, dpi=150)`**:
   * Invokes `/usr/bin/pdftoppm -png -r 150 -f <P> -l <P>` to produce crisp page bitmaps.
3. **`ocr_gemini(image_path, api_key, preferred_model)`**:
   * Encodes the image to Base64 and posts a payload to Google's REST API endpoint.
   * **Automatic Cascade:** Tries `gemini-3.5-flash` $\rightarrow$ `gemini-3.5-flash-lite` $\rightarrow$ `gemini-3.1-flash-lite` $\rightarrow$ `gemini-3-flash-preview` on 503/429/404 responses.
4. **`ocr_openai(image_path, api_key, model="gpt-4o-mini")`**:
   * Alternative endpoint supporting OpenAI Vision models.
5. **`process_single_page(...)`**:
   * Manages the lifecycle of a single page: checks the cache $\rightarrow$ renders the image $\rightarrow$ invokes the Vision API $\rightarrow$ saves the output with up to 5 exponential retries.
6. **`parse_page_range(range_str, total_pages)`**:
   * Parses flexible page string inputs into a clean list of page integers.
7. **`main()`**:
   * Orchestrates the thread pool (`ThreadPoolExecutor`), tracks progress, and concatenates all `page_XXX.txt` files into `<book>_extracted.txt`.

---

## 4. Key Engineering Safeguards

* **Zero-Loss Resume / Smart Caching:** If `output/<book>/pages/page_XXX.txt` exists and is non-empty, the page is skipped immediately. This prevents accidental duplicate API billing if the script is interrupted.
* **Tashkeel-Preserving Prompt:** The embedded `SYSTEM_PROMPT` enforces strict preservation of Arabic vocalization (*Zabar, Zer, Pesh, Sukun, Tanween, Shaddah*) and structures tables into Markdown format while actively discarding background watermarks.
* **Exponential Backoff:** If the API encounters a temporary spike or rate limit, it backs off iteratively (`time.sleep(2 * attempt)`) up to 5 times before failing.

---

## 5. Usage Examples

```bash
# 1. Quick test on a single page (e.g. grammar table on page 18)
./ocr_vision_pipeline.py -f aag.pdf -p 18

# 2. Test a sample range (pages 1 to 5) with 2 workers
./ocr_vision_pipeline.py -f aag.pdf -p 1-5 -w 2

# 3. Full book extraction with 3 concurrent workers
./ocr_vision_pipeline.py -f lsq.pdf -p all -w 3

# 4. Use custom output directory and higher DPI
./ocr_vision_pipeline.py -f aag.pdf -p 1-10 -o my_output --dpi 200
```
