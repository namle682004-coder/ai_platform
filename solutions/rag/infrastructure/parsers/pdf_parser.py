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
from .ocr_text import clean_ocr_text, harmonize_diacritics
from .table_grid import append_columns, grid_from_pdf, render_table

# Rows of two tables on different pages within this distance (pt) are the same printed rows.
ROW_ALIGN_TOLERANCE = 2.0
MIN_STITCH_ROWS = 3


SCAN_MAX_TEXT_LAYER = 500
# Below this the embedded scan is too coarse to OCR as is and the page is rendered at `ocr_dpi` instead.
MIN_NATIVE_OCR_DPI = 150


def _ocr_token(page_idx: int) -> str:
    return f"\x00OCR{page_idx}\x00"


def _table_token(index: int) -> str:
    return f"\x00TABLE{index}\x00"


def stitch_column_pages(tables: List[Dict[str, Any]]) -> None:
    """
    A spreadsheet printed wider than the page puts the remaining columns of the same rows on later pages.
    Such a table has the same number of rows at the same vertical positions as an earlier one, and a first
    column that is not a repeat of the earlier table's (it continues it rather than repeating it). Its
    columns are appended to the earlier table, which is the one rendered.
    """
    for j, b in enumerate(tables):
        if len(b["tops"]) < MIN_STITCH_ROWS:
            continue
        for a in tables[:j]:
            if a["merged_into"] is not None or a["page"] >= b["page"] or len(a["tops"]) != len(b["tops"]):
                continue
            if any(abs(x - y) > ROW_ALIGN_TOLERANCE for x, y in zip(a["tops"], b["tops"], strict=True)):
                continue
            first_a = {row[0].text for row in a["grid"] if row and row[0].text}
            first_b = {row[0].text for row in b["grid"] if row and row[0].text}
            if first_a & first_b:
                continue
            a["grid"] = append_columns(a["grid"], b["grid"], ("stitch", a["page"], j))
            b["merged_into"] = a["page"]
            break


# A table ending in the last part of its page and one starting in the first part of the next page.
PAGE_EDGE_FRACTION = 0.2


def stitch_row_pages(tables: List[Dict[str, Any]]) -> None:
    """
    A table running past the bottom of a page continues at the top of the next page, usually without its
    header. The continuation (same number of columns) is appended to the first part; a repeated header row
    is dropped.
    """
    current: Optional[Dict[str, Any]] = None
    for t in tables:
        if t["merged_into"] is not None:
            continue
        continues = (
            current is not None
            and t["page"] == current["last_page"] + 1
            and current["y1"] >= current["height"] * (1 - PAGE_EDGE_FRACTION)
            and t["y0"] <= t["height"] * PAGE_EDGE_FRACTION
            and t["grid"] and current["grid"] and len(t["grid"][0]) == len(current["grid"][0])
        )
        if not continues:
            current = t
            continue
        rows = t["grid"]
        if [c.text for c in rows[0]] == [c.text for c in current["grid"][0]]:
            rows = rows[1:]  # header repeated on the new page
        current["grid"] = current["grid"] + rows
        current["last_page"], current["y1"] = t["page"], t["y1"]
        t["merged_into"] = current["page"]

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

    @staticmethod
    def _scan_image(page: Any) -> Optional[Any]:
        """
        The page's own scan image when one image covers the page: OCR of the original pixels reads diacritics
        better than a re-rendered (resampled) page. None when the page is not a single scanned image.
        """
        try:
            from PIL import Image
            images = page.get_images(full=True)
            if len(images) != 1:
                return None
            rects = page.get_image_rects(images[0][0])
            area = page.rect.width * page.rect.height or 1.0
            if not rects or (rects[0].width * rects[0].height) / area < 0.8:
                return None
            data = page.parent.extract_image(images[0][0])
            img = Image.open(io.BytesIO(data["image"]))
            # Scans stored at a very low resolution are upsampled to the configured OCR resolution.
            native_dpi = img.width / (rects[0].width / 72.0)
            if native_dpi < MIN_NATIVE_OCR_DPI:
                return None
            return img.convert("L")
        except Exception as exc:  # noqa: BLE001 - the rendered page is the fallback
            logger.debug("Scan image extraction failed: %s", exc)
            return None

    def _try_ocr_fallback(self, page: Any) -> Optional[str]:
        """
        OCR of a scanned page with Tesseract. Tesseract's own text output comes first: PyMuPDF's OCR text page
        rebuilds words from glyph boxes and drops the space after Vietnamese syllables with stacked diacritics
        ("vịsựnghiệp"), so it is only the fallback when pytesseract is missing.
        """
        dpi, languages = rag_settings.ocr_dpi, rag_settings.ocr_languages
        try:
            import pytesseract
            from PIL import Image
            img = self._scan_image(page)
            if img is None:
                img = Image.open(io.BytesIO(page.get_pixmap(dpi=dpi).tobytes("png")))
            text = pytesseract.image_to_string(img, lang=languages, config="--oem 1 --psm 3",
                                               timeout=rag_settings.ocr_page_timeout_seconds)
            if text and len(text.strip()) > 20:
                return text.strip()
        except RuntimeError as exc:
            # Tesseract ran but exceeded its time budget: the page is skipped. The fallback below has no
            # time limit and would hold the worker on exactly the page that is too slow.
            logger.warning("OCR of a scanned page timed out after %.0fs: page skipped (%s)",
                           rag_settings.ocr_page_timeout_seconds, exc)
            return None
        except Exception as exc:
            logger.debug("Pytesseract OCR unavailable: %s", exc)

        try:
            if hasattr(page, "get_textpage_ocr"):
                tp = page.get_textpage_ocr(language=languages, dpi=dpi, full=True)
                text = tp.extractText()
                if text and len(text.strip()) > 20:
                    return text.strip()
        except Exception as exc:
            logger.debug("PyMuPDF OCR fallback unavailable: %s", exc)

        logger.warning("Scanned page could not be OCRed (Tesseract with '%s' not available): its text is not indexed", languages)
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
            # Tables are rendered after every page is read: a table may continue on later pages (columns).
            tables: List[Dict[str, Any]] = []
            page_payloads: List[Tuple[int, str]] = []
            ocr_pages: Dict[int, str] = {}  # OCR text is corrected across the whole document before use
            ocr_attempted: List[int] = []
            ocr_failed: List[int] = []
            ocr_skipped: List[int] = []

            for page_idx, page in enumerate(doc, start=1):
                page_items: List[Tuple[float, float, str, str]] = []  # (y0, x0, type, content)
                table_bboxes: List[Tuple[float, float, float, float]] = []

                # 1. Detect tabular structures and extract as structured Markdown tables (PyMuPDF find_tables)
                try:
                    if hasattr(page, "find_tables"):
                        tabs = page.find_tables()
                        for tab in tabs:
                            try:
                                grid = grid_from_pdf(tab.extract(), (page_idx, len(tables)))
                                if any(c.text for row in grid for c in row):
                                    tb_x0, tb_y0, tb_x1, tb_y1 = tab.bbox
                                    page_items.append((tb_y0, tb_x0, "table", _table_token(len(tables))))
                                    table_bboxes.append((tb_x0, tb_y0, tb_x1, tb_y1))
                                    tables.append({
                                        "page": page_idx, "last_page": page_idx, "grid": grid, "merged_into": None,
                                        "tops": [row.bbox[1] for row in tab.rows],
                                        "y0": tb_y0, "y1": tb_y1, "height": page.rect.height,
                                        "chars": sum(len(c.text) for row in grid for c in row),
                                    })
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
                    for ty0, _tx0, ttype, tcontent in page_items:
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

                page_tables = [t for t in tables if t["page"] == page_idx]
                raw_text_length = sum(len(content) for _, _, item_type, content in page_items if item_type == "text")
                raw_text_length += sum(t["chars"] for t in page_tables)
                # A page image covering the page with (almost) no text layer is a scan. Signed scans carry a
                # small text overlay (the signature stamp), so "almost no text" is a few hundred characters.
                is_scanned_page = (image_area_sum / page_area >= 0.8) and (raw_text_length < SCAN_MAX_TEXT_LAYER)
                if is_scanned_page and len(ocr_attempted) >= rag_settings.ocr_max_pages:
                    ocr_skipped.append(page_idx)  # budget per document: a huge scan must not hold the worker
                elif is_scanned_page:
                    logger.info(
                        "Page %d of PDF '%s' identified as SCANNED document (Image Coverage: %.1f%%, Text Length: %d). Triggering OCR Fallback.",
                        page_idx, filename, (image_area_sum / page_area) * 100, raw_text_length
                    )
                    ocr_attempted.append(page_idx)
                    ocr_text = clean_ocr_text(self._try_ocr_fallback(page) or "")
                    if not ocr_text:
                        ocr_failed.append(page_idx)
                    if ocr_text:
                        ocr_pages[page_idx] = ocr_text
                        page_items.append((0.0, 0.0, "text", f"[Văn bản nhận dạng quang học OCR Trang {page_idx}]\n{_ocr_token(page_idx)}"))

                # 4. Sort text and images by spatial coordinates (y-axis reading order: top to bottom)
                page_items.sort(key=lambda item: (item[0], item[1]))

                # 5. Assemble merged page content, ensuring images directly follow preceding step
                assembled_blocks: List[str] = []
                for _, _, _item_type, content in page_items:
                    assembled_blocks.append(content)

                page_text = "\n\n".join(assembled_blocks).strip()
                page_payloads.append((page_idx, page_text))

            stitch_column_pages(tables)
            stitch_row_pages(tables)
            ocr_order = sorted(ocr_pages)
            ocr_fixed = dict(zip(ocr_order, harmonize_diacritics([ocr_pages[p] for p in ocr_order]), strict=True))
            for page_idx, page_text in page_payloads:
                if page_idx in ocr_fixed:
                    page_text = page_text.replace(_ocr_token(page_idx), ocr_fixed[page_idx])
                for i, t in enumerate(tables):
                    token = _table_token(i)
                    if token in page_text:
                        page_text = page_text.replace(token, "" if t["merged_into"] is not None else render_table(t["grid"]))
                page_text = "\n\n".join(b for b in page_text.split("\n\n") if b.strip())
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
                    # Scanned pages without indexed text (OCR failed / over the per-document budget): reported
                    # on the document so a partially readable scan is visible, not silently incomplete.
                    "ocr_pages": len(ocr_attempted) - len(ocr_failed),
                    "ocr_failed_pages": ocr_failed,
                    "ocr_skipped_pages": ocr_skipped,
                    "images_count": len(all_extracted_images),
                    "images": all_extracted_images,
                    "embedded_files_count": embedded_files_count,
                },
            )
        except Exception as exc:
            logger.error("Failed to parse PDF document '%s': %s", filename, exc)
            raise DocumentParsingError(f"PDF parsing failed: {exc}") from exc
