"""
PDF Parser implementation using PyMuPDF (fitz).
Extracts text and aligns embedded images (Image XObjects) according to 2D spatial coordinates (y-axis order).
Extracts embedded file attachments recursively.
"""

from __future__ import annotations

import hashlib
import io
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

try:
    import pypdf
except ImportError:
    pypdf = None

from ...config import rag_settings
from ...domain.entities import ParsedDocument, ParsedPage
from ...domain.exceptions import DocumentParsingError
from .base import BaseDocumentParser

logger = logging.getLogger("aip-rag.parser.pdf")


class PdfDocumentParser(BaseDocumentParser):
    """
    Parser for Adobe PDF documents with full 2D multimodal text-image alignment.
    Honors vertical reading order (y-axis coordinate alignment) to ensure screenshots
    appear directly below their corresponding instruction step.
    """

    def __init__(
        self,
        base_storage_url: str = "https://storage.enterprise.internal/media",
    ):
        self.base_storage_url = base_storage_url.rstrip("/")

    def _try_ocr_fallback(self, page: Any) -> Optional[str]:
        """
        Attempts OCR on a scanned PDF page using PyMuPDF get_textpage_ocr or external pytesseract.
        """
        try:
            if hasattr(page, "get_textpage_ocr"):
                tp = page.get_textpage_ocr(language="vie+eng", dpi=150)
                text = tp.extractText()
                if text and len(text.strip()) > 20:
                    return text.strip()
        except Exception as exc:
            logger.debug("PyMuPDF built-in OCR fallback unavailable: %s", exc)

        try:
            import pytesseract
            from PIL import Image
            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img, lang="vie+eng")
            if text and len(text.strip()) > 20:
                return text.strip()
        except Exception as exc:
            logger.debug("Pytesseract OCR fallback unavailable: %s", exc)

        return None

    def parse(
        self,
        file_bytes: bytes,
        filename: str,
        depth: int = 0,
        max_depth: Optional[int] = None,
        max_file_size: Optional[int] = None,
        max_files_count: Optional[int] = None,
    ) -> ParsedDocument:
        if max_depth is None:
            try:
                max_depth = rag_settings.pdf_max_depth
            except Exception:
                max_depth = 3
        if max_file_size is None:
            try:
                max_file_size = rag_settings.max_embedded_file_size_bytes
            except Exception:
                max_file_size = 20 * 1024 * 1024
        if max_files_count is None:
            try:
                max_files_count = rag_settings.max_embedded_files_count
            except Exception:
                max_files_count = 10
        if fitz is None and pypdf is None:
            raise DocumentParsingError("PDF parsing failed: neither pymupdf nor pypdf is installed in this runtime.")

        if fitz is None and pypdf is not None:
            try:
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                pages: List[ParsedPage] = []
                for idx, page in enumerate(reader.pages, start=1):
                    txt = page.extract_text() or ""
                    clean_t = txt.strip()
                    if clean_t:
                        pages.append(ParsedPage(page_number=idx, text=clean_t))
                if not pages:
                    pages.append(ParsedPage(page_number=1, text=""))
                return ParsedDocument(
                    filename=filename,
                    file_type="pdf",
                    pages=pages,
                    metadata={"total_pages": len(pages), "images_count": 0, "images": [], "embedded_files_count": 0},
                )
            except Exception as exc:
                logger.error("Failed to parse PDF with pypdf fallback: %s", exc)
                raise DocumentParsingError(f"PDF parsing failed: {exc}") from exc

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            pages: List[ParsedPage] = []
            all_extracted_images: List[Dict[str, Any]] = []
            seen_image_hashes = set()

            for page_idx, page in enumerate(doc, start=1):
                page_items: List[Tuple[float, float, str, str]] = []  # (y0, x0, type, content)
                table_bboxes: List[Tuple[float, float, float, float]] = []

                # 1. Detect tabular structures and extract as structured Markdown tables (PyMuPDF find_tables)
                try:
                    if hasattr(page, "find_tables"):
                        tabs = page.find_tables()
                        for tab in tabs:
                            try:
                                md = tab.to_markdown()
                                if md and md.strip():
                                    tb_x0, tb_y0, tb_x1, tb_y1 = tab.bbox
                                    page_items.append((tb_y0, tb_x0, "table", md.strip()))
                                    table_bboxes.append((tb_x0, tb_y0, tb_x1, tb_y1))
                            except Exception as tab_err:
                                logger.debug("Failed to extract markdown table on page %d: %s", page_idx, tab_err)
                except Exception as tabs_exc:
                    logger.debug("page.find_tables() failed on page %d: %s", page_idx, tabs_exc)

                # 2. Extract text blocks with 2D bounding boxes (x0, y0, x1, y1, text, block_no, block_type)
                text_blocks = page.get_text("blocks")
                for blk in text_blocks:
                    # blk[6] is block_type (0 = text, 1 = image)
                    is_text = (blk[6] == 0) if len(blk) > 6 else True
                    if len(blk) >= 5 and is_text:
                        x0, y0, x1, y1, text_content = blk[0], blk[1], blk[2], blk[3], blk[4]
                        # Skip if block falls inside an already extracted table to avoid duplicate messy text
                        if table_bboxes:
                            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                            if any(tx0 - 3 <= cx <= tx1 + 3 and ty0 - 3 <= cy <= ty1 + 3 for tx0, ty0, tx1, ty1 in table_bboxes):
                                continue
                        clean_t = text_content.strip()
                        if clean_t:
                            page_items.append((y0, x0, "text", clean_t))

                # 2. Extract image XObjects and get their 2D bounding boxes on the page
                image_list = page.get_images(full=True)
                for img_info in image_list:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image.get("image", b"")
                    image_ext = base_image.get("ext", "png")

                    if not image_bytes or len(image_bytes) < 100:
                        continue  # Skip 0-byte or tiny icon artifacts

                    image_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
                    image_url = f"{self.base_storage_url}/{image_hash}.{image_ext}"

                    if image_hash not in seen_image_hashes:
                        seen_image_hashes.add(image_hash)
                        all_extracted_images.append({
                            "hash": image_hash,
                            "url": image_url,
                            "ext": image_ext,
                            "size_bytes": len(image_bytes),
                            "page_number": page_idx,
                            "data": image_bytes,
                        })

                    # Get 2D spatial coordinate of image on this page
                    rects = page.get_image_rects(xref)
                    if rects:
                        rect = rects[0]
                        img_y0 = rect.y0
                        img_x0 = rect.x0
                    else:
                        img_y0 = 9999.0
                        img_x0 = 0.0

                    # BRD-RAG-02: Detect preceding step label from text blocks above image
                    step_label = None
                    for ty0, tx0, ttype, tcontent in page_items:
                        if ttype == "text" and ty0 < img_y0:
                            lower_t = tcontent.strip().lower()
                            for prefix in ("bước", "step", "thao tác"):
                                if lower_t.startswith(prefix):
                                    step_label = tcontent.strip().split("\n")[0].strip("# *")
                                    break
                    img_caption = step_label or f"Ảnh minh họa Trang {page_idx}"
                    img_md = f"![{img_caption}]({image_url})"
                    page_items.append((img_y0, img_x0, "image", img_md))

                # 3. Detect Scanned Page & Trigger OCR Fallback (FR-ING-08 / ING-RAG-08)
                page_area = (page.rect.width * page.rect.height) if (page.rect.width and page.rect.height) else 1.0
                image_area_sum = 0.0
                for img_info in image_list:
                    xref = img_info[0]
                    for r in page.get_image_rects(xref):
                        image_area_sum += (r.width * r.height)

                raw_text_length = sum(len(content) for _, _, item_type, content in page_items if item_type in ("text", "table"))
                is_scanned_page = (image_area_sum / page_area >= 0.8) and (raw_text_length < 50)
                if is_scanned_page:
                    logger.info(
                        "Page %d of PDF '%s' identified as SCANNED document (Image Coverage: %.1f%%, Text Length: %d). Triggering OCR Fallback.",
                        page_idx, filename, (image_area_sum / page_area) * 100, raw_text_length
                    )
                    ocr_text = self._try_ocr_fallback(page)
                    if ocr_text:
                        page_items.append((0.0, 0.0, "text", f"[Văn bản nhận dạng quang học OCR Trang {page_idx}]\n{ocr_text}"))

                # 4. Sort text and images by spatial coordinates (y-axis reading order: top to bottom)
                page_items.sort(key=lambda item: (item[0], item[1]))

                # 5. Assemble merged page content, ensuring images directly follow preceding step
                assembled_blocks: List[str] = []
                for _, _, item_type, content in page_items:
                    assembled_blocks.append(content)

                page_text = "\n\n".join(assembled_blocks).strip()
                pages.append(ParsedPage(page_number=page_idx, text=page_text))

            # 5. Extract embedded files (PDF attachments) recursively if present (guarded by max_depth & size checks)
            embedded_files_count = 0
            try:
                all_emb_names = doc.embfile_names() if hasattr(doc, "embfile_names") else []
                if all_emb_names:
                    if depth >= max_depth:
                        logger.warning(
                            "PDF recursion guard: recursion limit reached (depth=%d >= max_depth=%d) for document '%s' with %d attachments. Skipping nested parsing.",
                            depth, max_depth, filename, len(all_emb_names)
                        )
                    else:
                        target_emb_names = all_emb_names[:max_files_count]
                        if len(all_emb_names) > max_files_count:
                            logger.warning(
                                "PDF attachment count limit: '%s' has %d attachments, only processing first %d.",
                                filename, len(all_emb_names), max_files_count
                            )

                        for emb_name in target_emb_names:
                            try:
                                emb_bytes = doc.embfile_get(emb_name)
                                if not emb_bytes:
                                    continue

                                # Anti-Zip-Bomb / Size Guard
                                if len(emb_bytes) > max_file_size:
                                    logger.warning(
                                        "PDF bomb guard: Embedded file '%s' in '%s' exceeds maximum allowed size (%d > %d bytes). Skipping attachment.",
                                        emb_name, filename, len(emb_bytes), max_file_size
                                    )
                                    continue

                                if emb_name.lower().endswith(".pdf"):
                                    sub_pdf_parser = PdfDocumentParser(base_storage_url=self.base_storage_url)
                                    sub_doc = sub_pdf_parser.parse(
                                        emb_bytes,
                                        filename=f"{filename}::{emb_name}",
                                        depth=depth + 1,
                                        max_depth=max_depth,
                                        max_file_size=max_file_size,
                                        max_files_count=max_files_count,
                                    )
                                    for sp in sub_doc.pages:
                                        pages.append(ParsedPage(page_number=len(pages) + 1, text=f"[Đính kèm: {emb_name}]\n{sp.text}"))
                                    all_extracted_images.extend(sub_doc.metadata.get("images", []))
                                    embedded_files_count += 1
                            except Exception as sub_exc:
                                logger.warning("Failed to extract or parse embedded attachment '%s' in '%s': %s", emb_name, filename, sub_exc)
            except Exception as emb_exc:
                logger.debug("No attachments or error checking embedded files in '%s': %s", filename, emb_exc)

            doc.close()

            logger.info(
                "Parsed PDF '%s': %d pages, %d images extracted & anchored, %d embedded files",
                filename, len(pages), len(all_extracted_images), embedded_files_count
            )

            return ParsedDocument(
                filename=filename,
                file_type="pdf",
                pages=pages,
                metadata={
                    "total_pages": len(pages),
                    "images_count": len(all_extracted_images),
                    "images": all_extracted_images,
                    "embedded_files_count": embedded_files_count,
                },
            )
        except Exception as exc:
            logger.error("Failed to parse PDF document '%s': %s", filename, exc)
            raise DocumentParsingError(f"PDF parsing failed: {exc}") from exc
