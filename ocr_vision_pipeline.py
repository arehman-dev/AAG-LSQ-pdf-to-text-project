#!/usr/bin/env python3
"""
Urdu & Arabic Vision OCR Pipeline for PDF Documents.
Uses Multimodal Vision LLMs (Google Gemini API / OpenAI API) to accurately transcribe
mixed Urdu Nastaliq and vocalized Arabic (with full Tashkeel/diacritics), ignoring watermarks.
"""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
import requests

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

GEMINI_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
]

def load_dotenv():
    """Simple loader for .env file in the current directory or parent directory."""
    for p in [Path(".env"), Path(__file__).parent / ".env"]:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v

def extract_page_image(pdf_path: str, page_num: int, output_img_path: str, dpi: int = 150) -> bool:
    """Render a single PDF page to a PNG image using pdftoppm."""
    out_prefix = output_img_path.rsplit(".png", 1)[0]
    cmd = [
        "pdftoppm",
        "-png",
        "-r", str(dpi),
        "-f", str(page_num),
        "-l", str(page_num),
        pdf_path,
        out_prefix
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        print(f"[!] Error extracting page {page_num}: {res.stderr.decode('utf-8', errors='ignore')}", file=sys.stderr)
        return False
    
    generated_files = sorted(list(Path(out_prefix).parent.glob(f"{Path(out_prefix).name}*.png")))
    if not generated_files:
        print(f"[!] No image generated for page {page_num}", file=sys.stderr)
        return False
    
    generated_file = generated_files[0]
    if str(generated_file) != output_img_path:
        generated_file.rename(output_img_path)
    return True

def ocr_gemini(image_path: str, api_key: str, preferred_model: str = None) -> str:
    """Call Google Gemini REST API with automatic model fallback."""
    if preferred_model:
        models_to_try = [preferred_model] + [m for m in GEMINI_MODELS if m != preferred_model]
    else:
        models_to_try = GEMINI_MODELS

    with open(image_path, "rb") as f:
        img_bytes = f.read()
    b64_data = base64.b64encode(img_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64_data
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1
        }
    }
    headers = {"Content-Type": "application/json"}

    last_err = None
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                candidate = data["candidates"][0]
                return candidate["content"]["parts"][0]["text"]
            elif response.status_code in (404, 503, 429):
                last_err = f"Model {model} returned {response.status_code}: {response.text[:120]}"
                continue
            else:
                response.raise_for_status()
        except Exception as e:
            last_err = str(e)
            continue

    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")

def ocr_openai(image_path: str, api_key: str, model: str = "gpt-4o-mini") -> str:
    """Call OpenAI Chat Completions REST API."""
    url = "https://api.openai.com/v1/chat/completions"

    with open(image_path, "rb") as f:
        img_bytes = f.read()
    b64_data = base64.b64encode(img_bytes).decode("utf-8")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": SYSTEM_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_data}"
                        }
                    }
                ]
            }
        ],
        "temperature": 0.1
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"OpenAI API Error {response.status_code}: {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]

def parse_page_range(range_str: str, total_pages: int):
    """Parse string range like '1-10', '5', '1,3,5-7', or 'all'."""
    if range_str.lower() == "all":
        return list(range(1, total_pages + 1))
    pages = set()
    parts = range_str.split(",")
    for part in parts:
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.update(range(int(start), min(int(end), total_pages) + 1))
        else:
            p = int(part)
            if 1 <= p <= total_pages:
                pages.add(p)
    return sorted(list(pages))

def get_pdf_page_count(pdf_path: str) -> int:
    """Get total pages using pdfinfo."""
    res = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True)
    for line in res.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise ValueError(f"Could not determine page count for {pdf_path}")

def process_single_page(page_num: int, total_pages: int, pdf_path: str, pages_out: Path, images_cache: Path, args, api_key: str) -> bool:
    page_txt_file = pages_out / f"page_{page_num:03d}.txt"
    page_img_file = images_cache / f"page_{page_num:03d}.png"

    if page_txt_file.exists() and page_txt_file.stat().st_size > 0:
        print(f"[{page_num:>3}/{total_pages}] [Cached/Skipped]")
        return True

    if not page_img_file.exists():
        if not extract_page_image(pdf_path, page_num, str(page_img_file), dpi=args.dpi):
            print(f"[{page_num:>3}/{total_pages}] Failed to extract image.")
            return False

    max_retries = 5
    ocr_result = None
    for attempt in range(1, max_retries + 1):
        try:
            if args.provider == "gemini":
                ocr_result = ocr_gemini(str(page_img_file), api_key, preferred_model=args.model)
            else:
                ocr_result = ocr_openai(str(page_img_file), api_key, model=args.model)
            break
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2 * attempt)
            else:
                print(f"[{page_num:>3}/{total_pages}] FAILED after {max_retries} attempts ({e})")
                return False

    if ocr_result:
        with open(page_txt_file, "w", encoding="utf-8") as f:
            f.write(ocr_result.strip() + "\n")
        print(f"[{page_num:>3}/{total_pages}] ✓ Saved")
        return True
    return False

def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="OCR Urdu and Arabic PDFs using Vision LLMs.")
    parser.add_argument("--file", "-f", required=True, help="PDF file path (e.g. aag.pdf or lsq.pdf)")
    parser.add_argument("--pages", "-p", default="1-5", help="Page range to process (e.g. '1-5', '18', '1-50', 'all')")
    parser.add_argument("--provider", choices=["gemini", "openai"], default="gemini", help="Vision LLM provider (default: gemini)")
    parser.add_argument("--model", default="gemini-3.5-flash", help="Specific model name (default: gemini-3.5-flash)")
    parser.add_argument("--api-key", default=None, help="API key (or set GEMINI_API_KEY / OPENAI_API_KEY in .env)")
    parser.add_argument("--output-dir", "-o", default="output", help="Directory for output files")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for extracted page images (default: 150)")
    parser.add_argument("--workers", "-w", type=int, default=2, help="Number of concurrent worker threads (default: 2)")
    parser.add_argument("--no-combine", action="store_true", help="Do not combine extracted pages into a single full file")

    args = parser.parse_args()

    pdf_path = os.path.abspath(args.file)
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    book_slug = Path(pdf_path).stem
    total_pages = get_pdf_page_count(pdf_path)
    pages_to_process = parse_page_range(args.pages, total_pages)

    # API Key check
    api_key = args.api_key
    if not api_key:
        if args.provider == "gemini":
            api_key = os.environ.get("GEMINI_API_KEY")
        else:
            api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        var_name = "GEMINI_API_KEY" if args.provider == "gemini" else "OPENAI_API_KEY"
        print(f"Error: API key not provided. Either pass --api-key or set the {var_name} environment variable / .env file.", file=sys.stderr)
        sys.exit(1)

    # Directories
    base_out = Path(args.output_dir) / book_slug
    pages_out = base_out / "pages"
    images_cache = base_out / "images"
    pages_out.mkdir(parents=True, exist_ok=True)
    images_cache.mkdir(parents=True, exist_ok=True)

    print(f"=== Starting Vision OCR for {Path(pdf_path).name} ===")
    print(f"Total Pages in PDF: {total_pages}")
    print(f"Pages to Process: {len(pages_to_process)} ({args.pages})")
    print(f"Provider: {args.provider.upper()} | Model: {args.model}")
    print(f"Workers: {args.workers}")
    print(f"Output Directory: {pages_out}\n")

    start_time = time.time()
    success_count = 0

    if args.workers > 1 and len(pages_to_process) > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_single_page, p, total_pages, pdf_path, pages_out, images_cache, args, api_key): p
                for p in pages_to_process
            }
            for fut in as_completed(futures):
                try:
                    if fut.result():
                        success_count += 1
                except Exception as ex:
                    print(f"[!] Worker exception: {ex}")
    else:
        for p in pages_to_process:
            if process_single_page(p, total_pages, pdf_path, pages_out, images_cache, args, api_key):
                success_count += 1

    print(f"\nProcessing Complete! ({success_count}/{len(pages_to_process)} pages succeeded in {time.time() - start_time:.1f}s)")

    # Combine into single file
    if not args.no_combine:
        combined_file = base_out / f"{book_slug}_extracted.txt"
        print(f"Generating combined book file: {combined_file} ...")
        
        all_page_files = sorted(pages_out.glob("page_*.txt"))
        with open(combined_file, "w", encoding="utf-8") as out:
            for pf in all_page_files:
                p_num_match = re.search(r"page_(\d+)\.txt", pf.name)
                p_label = p_num_match.group(1) if p_num_match else pf.stem
                out.write(f"\n\n{'='*30} [PAGE {int(p_label)}] {'='*30}\n\n")
                with open(pf, "r", encoding="utf-8") as f:
                    out.write(f.read().strip() + "\n")
        print(f"✓ Combined file updated: {combined_file} ({combined_file.stat().st_size:,} bytes)")

if __name__ == "__main__":
    main()
