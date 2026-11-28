import base64
import html
import shutil
from pathlib import Path
import fitz  # PyMuPDF
from openai import OpenAI
from app.core import usage
from app.core.models import model_request
import re
import subprocess
from datetime import datetime

class PDFHandler:
    """Handler for PDF file processing"""

    @staticmethod
    def generate_page_images(pdf_path, output_dir, max_height=2000, dpi=150, pages=None):
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)

        with fitz.open(pdf_path) as pdf:
            page_count = len(pdf)
            if pages is None:
                page_numbers = list(range(page_count))
            else:
                page_numbers = sorted({
                    int(page) for page in pages
                    if 0 <= int(page) < page_count
                })
            for page_num in page_numbers:
                page = pdf.load_page(page_num)
                
                # Calculate the scaling factor for the desired DPI
                scale = dpi / 72  # Default DPI in PyMuPDF is 72
                
                # Generate the pixmap with the scaling factor
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
                
                # Resize image if height exceeds max_height
                if pix.height > max_height:
                    scale = max_height / pix.height
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
                
                image_path = output_dir / f"page_{page_num:04d}.png"
                pix.save(image_path)
                #print(f"Saved image: {image_path}")

        print(f"{len(page_numbers)} pages saved as images in {output_dir.name}")

    @staticmethod
    def encode_image(image_path):
        """Encode image to base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    @staticmethod
    def remove_line_height_styles(html_content):
        """Remove all line-height styles from the HTML content"""
        return re.sub(r'line-height:\s*\d+(\.\d+)?;', '', html_content)

    @staticmethod
    def sanitize_html_output(html_content):
        """Sanitize the HTML output by removing markdown code block markers and line-height styles"""
        lines = html_content.split('\n')
        if lines[0].strip() == "```html":
            lines = lines[1:]
        if lines[-1].strip() == "```":
            lines = lines[:-1]
        sanitized_content = '\n'.join(lines)
        # Model HTML frequently contains empty/dangling anchors. PyMuPDF
        # tries to turn those into PDF links and raises ``No destination``.
        # Keep the readable text while dropping only anchor wrappers.
        sanitized_content = re.sub(r'<a\b[^>]*>', '', sanitized_content, flags=re.IGNORECASE)
        sanitized_content = re.sub(r'</a\s*>', '', sanitized_content, flags=re.IGNORECASE)
        return PDFHandler.remove_line_height_styles(sanitized_content)

    @staticmethod
    def insert_htmlbox_safe(page, rect, html_content):
        """Render HTML and fall back to plain text for malformed provider HTML."""
        try:
            return page.insert_htmlbox(rect, html_content)
        except RuntimeError as exc:
            if "destination" not in str(exc).lower() and "target_id" not in str(exc).lower():
                raise
            stripped = re.sub(r'</?a\b[^>]*>', '', html_content, flags=re.IGNORECASE)
            try:
                return page.insert_htmlbox(rect, stripped)
            except RuntimeError:
                text = html.unescape(re.sub(r'<[^>]+>', ' ', stripped))
                return page.insert_textbox(rect, text, fontsize=10, fontname="helv")

    @staticmethod
    def compress_pdf(input_pdf_path, output_pdf_path):
        """Compress with Ghostscript when available, otherwise keep PDF usable."""
        input_pdf_path = Path(input_pdf_path)
        output_pdf_path = Path(output_pdf_path)
        ghostscript = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
        if not ghostscript:
            shutil.copy2(input_pdf_path, output_pdf_path)
            print("Ghostscript not found; using the uncompressed PDF output.")
            return output_pdf_path
        try:
            subprocess.run([
                ghostscript,
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.4',
                '-dPDFSETTINGS=/screen',
                '-dSubsetFonts=true',
                '-dEmbedAllFonts=true',
                '-dCompressFonts=true',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                f'-sOutputFile={output_pdf_path}',
                input_pdf_path
            ], check=True)
            print(f"Compressed PDF saved to {output_pdf_path.name}")
        except (subprocess.CalledProcessError, OSError) as e:
            # Compression is optional. Preserve the successfully rendered PDF
            # instead of failing the entire translation job.
            shutil.copy2(input_pdf_path, output_pdf_path)
            print(f"PDF compression skipped ({e}); using the uncompressed PDF output.")
        return output_pdf_path

    @staticmethod
    def _chapter_page_index(chapter_map, chunk_id):
        """Return the 0-based source page for a chunk, or ``None``."""
        location = (chapter_map or {}).get(chunk_id)
        if isinstance(location, dict):
            item = location.get("item", "")
        elif isinstance(location, (tuple, list)) and location:
            item = location[0]
        else:
            return None
        match = re.search(r"page_(\d+)", str(item or ""))
        return int(match.group(1)) if match else None

    @staticmethod
    def _text_block_rects(page):
        """Bounding boxes of the page's text blocks, ignoring empty ones."""
        rects = []
        try:
            blocks = page.get_text("blocks")
        except Exception:
            return rects
        for block in blocks:
            if len(block) < 5 or not str(block[4]).strip():
                continue
            rect = fitz.Rect(block[:4])
            if rect.is_empty or rect.width <= 0 or rect.height <= 0:
                continue
            rects.append(rect)
        return rects

    @staticmethod
    def _translation_rect(page, rects, margin=36):
        """The area the translation should occupy on the copied page."""
        page_rect = page.rect
        if rects:
            area = fitz.Rect(rects[0])
            for rect in rects[1:]:
                area |= rect
            pad = max(6.0, min(24.0, area.height * 0.15))
            area = fitz.Rect(
                margin,
                max(margin, area.y0 - pad),
                page_rect.width - margin,
                min(page_rect.height - margin, area.y1 + pad),
            )
        else:
            area = fitz.Rect(
                margin,
                margin,
                page_rect.width - margin,
                page_rect.height - margin,
            )
        if area.is_empty or area.width <= 1 or area.height <= 1:
            area = fitz.Rect(
                margin,
                margin,
                page_rect.width - margin,
                page_rect.height - margin,
            )
        return area

    @staticmethod
    def _insert_translated_page(doc, original_doc, page_index, html_content):
        """Copy one source page, remove its text only, and add the translation.

        ``apply_redactions`` is told to keep images and line art, so figures,
        charts and scanned illustrations survive while the original text is
        removed. The translation is then placed over the text area the source
        page used.
        """
        doc.insert_pdf(
            original_doc,
            from_page=page_index,
            to_page=page_index,
        )
        page = doc[-1]
        rects = PDFHandler._text_block_rects(page)
        for rect in rects:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        if rects:
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            )
        PDFHandler.insert_htmlbox_safe(
            page,
            PDFHandler._translation_rect(page, rects),
            html_content,
        )
        return page

    @staticmethod
    def save_translated_pdf(
        translations,
        output_pdf_path,
        original_pdf_path=None,
        chapter_map=None,
    ):
        """Write a translated PDF, keeping the source pages' images.

        When ``original_pdf_path`` and ``chapter_map`` are supplied, each source
        page is copied, its text is redacted while images and line art are kept,
        and the translation for that page is written over the original text
        area. Without them the old text-only page-per-chunk writer is used.
        """
        output_pdf_path = Path(output_pdf_path)  # Ensure it's a Path object
        temp_pdf_path = output_pdf_path.with_suffix('.temp.pdf')  # Temporary file for uncompressed PDF
        output_pdf_path.parent.mkdir(exist_ok=True)
        doc = fitz.open()
        page_width = 6.5 * 72  # inches to points
        page_height = 9.5 * 72
        margin = 0.5 * 72

        original_doc = None
        if original_pdf_path and chapter_map:
            try:
                original_doc = fitz.open(original_pdf_path)
            except Exception as exc:
                print(f"Warning: could not open source PDF for images ({exc}); using text-only pages.")

        try:
            if original_doc is not None:
                grouped = {}
                for chunk_id, html_content in translations.items():
                    page_index = PDFHandler._chapter_page_index(
                        chapter_map, chunk_id,
                    )
                    grouped.setdefault(page_index, []).append(
                        (chunk_id, html_content)
                    )

                for page_index in sorted(
                    grouped,
                    key=lambda value: (value is None, value if value is not None else 0),
                ):
                    items = sorted(
                        grouped[page_index],
                        key=lambda item: int(str(item[0]).split('-')[-1]),
                    )
                    html_content = "<br/>".join(
                        content for _, content in items
                    )
                    if page_index is not None and 0 <= page_index < len(original_doc):
                        try:
                            PDFHandler._insert_translated_page(
                                doc,
                                original_doc,
                                page_index,
                                html_content,
                            )
                            continue
                        except Exception as exc:
                            print(
                                f"Warning: could not preserve images on "
                                f"page {page_index + 1} ({exc}); "
                                f"using a text-only page."
                            )
                    page = doc.new_page(width=page_width, height=page_height)
                    PDFHandler.insert_htmlbox_safe(
                        page,
                        fitz.Rect(
                            margin,
                            margin,
                            page_width - margin,
                            page_height - margin,
                        ),
                        html_content,
                    )
            else:
                for chunk_id in sorted(
                    translations.keys(),
                    key=lambda x: int(x.split('-')[1]),
                ):
                    html_content = translations[chunk_id]
                    page = doc.new_page(width=page_width, height=page_height)
                    PDFHandler.insert_htmlbox_safe(
                        page,
                        fitz.Rect(
                            margin,
                            margin,
                            page_width - margin,
                            page_height - margin,
                        ),
                        html_content,
                    )
        finally:
            if original_doc is not None:
                original_doc.close()
        
        # Save the uncompressed PDF to a temporary file
        doc.save(temp_pdf_path)
        print(f"Uncompressed PDF saved to {temp_pdf_path.name}")

        # Compress the PDF using Ghostscript
        PDFHandler.compress_pdf(temp_pdf_path, output_pdf_path)
        # The uncompressed copy is a full-size duplicate. Leaving it in the
        # user's output directory doubled storage for every PDF-source job
        # (and the audit found one next to every translated.pdf).
        try:
            temp_pdf_path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def save_bilingual_pdf(
        original_pdf_path,
        translations,
        output_pdf_path,
        chapter_map=None,
    ):
        """Write a new PDF document alternating between original and translated pages."""
        output_pdf_path = Path(output_pdf_path)  # Ensure it's a Path object
        temp_pdf_path = output_pdf_path.with_suffix('.temp.pdf')  # Temporary file for uncompressed PDF
        original_pdf_path = Path(original_pdf_path)
        output_pdf_path.parent.mkdir(exist_ok=True)
        doc = fitz.open()
        page_width = 6.5 * 72  # inches to points
        page_height = 9.5 * 72
        margin = 0.5 * 72

        # Open the original PDF
        original_doc = fitz.open(original_pdf_path)

        for page_num in range(len(original_doc)):
            # Add original page
            original_page = original_doc.load_page(page_num)
            doc.insert_pdf(original_doc, from_page=page_num, to_page=page_num)

            # Add translated page
            if chapter_map:
                items = [
                    (chunk_id, content)
                    for chunk_id, content in translations.items()
                    if PDFHandler._chapter_page_index(chapter_map, chunk_id)
                    == page_num
                ]
                html_content = "<br/>".join(
                    content
                    for _, content in sorted(
                        items,
                        key=lambda item: int(str(item[0]).split('-')[-1]),
                    )
                )
            else:
                chunk_id = f'chunk-{page_num}'
                html_content = translations.get(chunk_id, "")

            if html_content:
                try:
                    PDFHandler._insert_translated_page(
                        doc,
                        original_doc,
                        page_num,
                        html_content,
                    )
                except Exception as exc:
                    print(
                        f"Warning: could not preserve images on "
                        f"page {page_num + 1} ({exc}); "
                        f"using a text-only page."
                    )
                    page = doc.new_page(
                        width=page_width,
                        height=page_height,
                    )
                    PDFHandler.insert_htmlbox_safe(
                        page,
                        fitz.Rect(
                            margin,
                            margin,
                            page_width - margin,
                            page_height - margin,
                        ),
                        html_content,
                    )

        # Save the uncompressed PDF to a temporary file
        doc.save(temp_pdf_path)
        print(f"Uncompressed PDF saved to {temp_pdf_path.name}")

        # Compress the PDF using Ghostscript
        PDFHandler.compress_pdf(temp_pdf_path, output_pdf_path)
        try:
            temp_pdf_path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def transcribe_pdf(client, input_pdf_path, paths, dpi=150, batch=False, model=None, pages=None):
        """Transcribe PDF pages with vision.

        ``pages`` (0-based) limits rendering and requests to those pages, which
        is how phase 3 sends only the figure/rejected pages of a mixed book to
        the provider. Chunk ids carry the real page number; the caller merges
        the groups with :func:`merge_page_chunks` to renumber them contiguously.
        """
        # The vision call used to hardcode "gpt-5.6-terra", so every PDF paid
        # for the transcription step with a model the user never chose. Resolve
        # it the same way the rest of the pipeline does.
        if model is None:
            from app.core.models import resolve_default_model
            model = resolve_default_model()
        input_pdf_path = Path(input_pdf_path)
        if not input_pdf_path.exists():
            print(f"Error: Input file not found: {input_pdf_path}")
            return

        # Create output directory
        output_dir = paths['job_dir']
        #output_dir.mkdir(exist_ok=True)

        # Clear temporary image dir
        for png_file in output_dir.glob("*.png"):
            png_file.unlink()

        # Generate images of PDF pages
        PDFHandler.generate_page_images(input_pdf_path, output_dir, dpi=dpi, pages=pages)

        all_chunks = []
        chapter_map = {}

        custompdfprompt = None
        custom_pdfprompt_path = Path("./custompdfprompt.txt")
        if custom_pdfprompt_path.exists():
            print(f"Using custompdfprompt.txt [transcribe_pdf]")
            with open(custom_pdfprompt_path, 'r', encoding='utf-8') as f:
                custompdfprompt = f.read()

        # if batch:
        #     # Create batch input file
        #     temp_dir = Path('./temp')
        #     temp_dir.mkdir(exist_ok=True)
        #     timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        #     batch_file_path = temp_dir / f"batch_input_{timestamp}.jsonl"
            
        #     with open(batch_file_path, "w", encoding="utf-8") as f:
        #         for page_num, image_path in enumerate(sorted(output_dir.glob("*.png"))):
        #             base64_image = PDFHandler.encode_image(image_path)
        #             request = {
        #                 "custom_id": f"chunk-{page_num}",
        #                 "method": "POST",
        #                 "url": "/v1/chat/completions",
        #                 "body": {
        #                     "model": "gpt-5.6-terra",
        #                     "messages": [
        #                         {
        #                             "role": "system",
        #                             "content": "The image is a scan of a page from a German scholarly book on Greek and Roman antiquity. Most of the text is in German, but there are also quotations in Greek and Latin. Your task is to understand the text, translate into ENGLISH while leaving any Greek and Latin quotations untranslated, and format the translated text as a HTML document as it would be in a scholarly translation. Accuracy is key. Pay special attention to FOOTNOTES, which are found at the bottom of the page in SMALLER font. Use 'font-family: serif' for the main text and 'font-family: Palatino' for Greek text. Do not use tables or line-height or any heading tags (e.g. <h1>). Return ONLY the HTML content, beginning with <!DOCTYPE html> and ending with </html>."
        #                         },
        #                         {
        #                             "role": "user",
        #                             "content": "Analyze the following image.",
        #                             "type": "image_url",
        #                             "image_url": {
        #                                 "url": f"data:image/png;base64,{base64_image}"
        #                             }
        #                         }
        #                     ]
        #                 }
        #             }
        #             f.write(json.dumps(request) + "\n")
            
        #     print(f"Batch input file created at {batch_file_path}")
        #     return batch_file_path

        # Process each image sequentially. The page number comes from the file
        # name, never from the render order, so a subset keeps its real page.
        image_paths = sorted(output_dir.glob("page_*.png"))
        for image_path in image_paths:
            page_num = int(image_path.stem.split("_")[-1])
            base64_image = PDFHandler.encode_image(image_path)
            #print(f"Transcribing {image_path}")

            print(f"Processing page {page_num + 1} of {len(image_paths)}")

            response = usage.call_stage(
                "pdf_vision", client.chat.completions.create,
                **model_request(model),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": custompdfprompt if custompdfprompt else "The image is a scan of a page from a German scholarly book on Greek and Roman antiquity. Most of the text is in German, but there are also quotations in Greek and Latin. Your task is to understand the text, translate into ENGLISH while leaving Greek and Latin quotations untranslated, and format the translated text as a HTML document as it would be in a scholarly translation. Accuracy is key. Pay special attention to FOOTNOTES, which are found at the bottom of the page in SMALLER font. If you encounter fragments of sentences, do not leave them out but do your best to translate them. Use 'font-family: serif' for the main text and 'font-family: Palatino' for Greek text. Do not use tables or line-height or any heading tags (e.g. <h1>). Return ONLY the HTML content, beginning with <!DOCTYPE html> and ending with </html>.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                            },
                        ],
                    }
                ],
            )

            html_content = response.choices[0].message.content
            sanitized_html_content = PDFHandler.sanitize_html_output(html_content)

            # Save HTML content to file
            html_file_path = output_dir / f"page_{page_num:04d}.html"
            with open(html_file_path, "w", encoding="utf-8") as html_file:
                html_file.write(sanitized_html_content)

            # Add to all_chunks and chapter_map
            chunk_id = f'chunk-{page_num}'
            all_chunks.append((chunk_id, sanitized_html_content))
            chapter_map[chunk_id] = {
                "item": f"page_{page_num}.html",
                "pos": 0
            }

        return all_chunks, chapter_map


_PAGE_INDEX_RE = re.compile(r"page_(\d+)")


def _page_index(item: str) -> int:
    match = _PAGE_INDEX_RE.search(str(item or ""))
    return int(match.group(1)) if match else 10 ** 9


def merge_page_chunks(*groups):
    """Merge page-ordered chunk groups into contiguous ``chunk-0..N`` ids.

    Each group is ``(chunks, chapter_map)`` as produced by ``pdf_text`` or
    ``PDFHandler.transcribe_pdf``. Chunks are ordered by their source page and
    then by position inside the page, so a book mixing locally extracted text
    with vision pages keeps the document order.

    Returns ``(all_chunks, chapter_map, id_map)``. ``id_map`` maps
    ``(group_index, old_chunk_id)`` to the new id, which lets the caller carry
    per-chunk context across the renumbering. Ids must stay contiguous because
    ``save_translated_pdf`` orders pages by ``int(chunk_id.split('-')[1])``.
    """
    merged = []
    for group_index, (chunks, chapter_map) in enumerate(groups):
        for chunk_id, text in chunks or []:
            location = (chapter_map or {}).get(chunk_id)
            if isinstance(location, dict):
                item = str(location.get("item", "") or "")
                position = int(location.get("pos", 0) or 0)
            elif isinstance(location, (tuple, list)) and location:
                item = str(location[0])
                position = int(location[1]) if len(location) > 1 else 0
            else:
                item, position = "", 0
            merged.append((_page_index(item), position, len(merged), group_index, chunk_id, text, item))

    merged.sort(key=lambda row: (row[0], row[1], row[2]))

    all_chunks = []
    chapter_map = {}
    id_map = {}
    for counter, row in enumerate(merged):
        _, position, _, group_index, old_id, text, item = row
        chunk_id = f"chunk-{counter}"
        all_chunks.append((chunk_id, text))
        chapter_map[chunk_id] = (item, position)
        id_map[(group_index, old_id)] = chunk_id
    return all_chunks, chapter_map, id_map


if __name__ == "__main__":
    PDFHandler.main()

