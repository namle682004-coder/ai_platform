"""
DOCX Parser implementation using python-docx and OpenXML inspection.
Extracts paragraphs, tables, and inline drawing images in exact document order.
Anchors screenshots directly below corresponding instruction steps.
Extracts embedded OLE object packages recursively.
"""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from typing import Any, Dict, List, Optional, Set

from ...domain.entities import ParsedDocument, ParsedPage
from ...domain.exceptions import DocumentParsingError
from .base import BaseDocumentParser
from .table_grid import GridCell, clean, render_table

logger = logging.getLogger("aip-rag.parser.docx")


class DocxDocumentParser(BaseDocumentParser):
    """
    Parser for Microsoft Word (.docx) documents with full table and multimodal image alignment support.
    Extracts inline screenshots from OpenXML drawing markup and embeds Markdown image links
    directly beneath the corresponding paragraph step.
    """

    def __init__(
        self,
        base_storage_url: str = "https://storage.enterprise.internal/media",
    ):
        self.base_storage_url = base_storage_url.rstrip("/")

    @staticmethod
    def _table_to_markdown(table) -> str:
        """
        Word table → Markdown via the shared table renderer. python-docx returns the same `_tc` element for
        every grid position of a merged cell (horizontal gridSpan and vertical vMerge), which is the merge key.
        """
        try:
            grid = [
                [GridCell(clean(cell.text), id(cell._tc)) for cell in row.cells]
                for row in table.rows
            ]
            return render_table(grid)
        except Exception as exc:
            logger.warning("Error converting Word table to Markdown: %s", exc)
            return ""

    @staticmethod
    def _heading_level(p) -> Optional[int]:
        """
        Markdown level (1-6) of a heading paragraph. Word's outline level (on the paragraph or inherited from
        its style chain) is used first: it is what the navigation pane shows and does not depend on the
        style's display name, which is localized ("Heading 1", "Tiêu đề 1", custom styles).
        """
        try:
            from docx.oxml.ns import qn

            sources = [p._p.pPr]
            style = getattr(p, "style", None)
            while style is not None:
                sources.append(style.element.pPr)
                style = style.base_style
            for ppr in sources:
                el = ppr.find(qn("w:outlineLvl")) if ppr is not None else None
                if el is not None:
                    level = int(el.get(qn("w:val")))
                    return level + 1 if level < 6 else None  # 9 = body text
        except Exception:  # noqa: BLE001 - fall back to the style name
            pass
        style_name = (getattr(getattr(p, "style", None), "name", "") or "").strip().lower()
        names = {"title": 1, "heading 1": 1, "subtitle": 2, "heading 2": 2, "heading 3": 3,
                 "heading 4": 4, "heading 5": 5, "heading 6": 6}
        return names.get(style_name)

    @classmethod
    def _format_paragraph(cls, p) -> str:
        """Format a Word paragraph, prefixing Markdown headings if its outline level / style is a heading."""
        txt = p.text.strip()
        if not txt:
            return ""
        level = cls._heading_level(p)
        if level:
            # A heading typed on several lines ("Chương I" / "QUY ĐỊNH CHUNG") is one heading: left multi-line,
            # its later lines would be taken for headings of their own and break the section hierarchy.
            return f"{'#' * level} {' – '.join(part.strip() for part in txt.splitlines() if part.strip())}"
        return txt

    def _extract_images_from_paragraph(
        self,
        p,
        doc,
        seen_hashes: Set[str],
        all_images: List[Dict[str, Any]],
        step_label: Optional[str] = None,
    ) -> List[str]:
        """
        Extracts inline DrawingML images from a paragraph element via OpenXML relationship mapping.
        Returns markdown image tags to append right below the paragraph.
        """
        image_tags: List[str] = []
        try:
            # 1. Standard DrawingML blip images (<a:blip r:embed="rIdX">)
            blip_nodes = p._p.xpath(".//a:blip")
            for blip in blip_nodes:
                r_id = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                if r_id and r_id in doc.part.related_parts:
                    img_part = doc.part.related_parts[r_id]
                    img_bytes = getattr(img_part, "blob", b"")
                    if not img_bytes or len(img_bytes) < 100:
                        continue

                    # Extract extension from content_type (e.g. image/png -> png)
                    content_type = getattr(img_part, "content_type", "image/png")
                    ext = content_type.split("/")[-1].replace("jpeg", "jpg") if "/" in content_type else "png"

                    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
                    img_url = f"{self.base_storage_url}/{img_hash}.{ext}"

                    if img_hash not in seen_hashes:
                        seen_hashes.add(img_hash)
                        all_images.append({
                            "hash": img_hash,
                            "url": img_url,
                            "ext": ext,
                            "size_bytes": len(img_bytes),
                            "data": img_bytes,
                        })

                    caption = step_label or "Ảnh minh họa"
                    image_tags.append(f"![{caption}]({img_url})")

            # 2. Legacy VML imagedata (<v:imagedata r:id="rIdX">)
            vml_nodes = p._p.xpath(".//v:imagedata")
            for vml in vml_nodes:
                r_id = vml.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                if r_id and r_id in doc.part.related_parts:
                    img_part = doc.part.related_parts[r_id]
                    img_bytes = getattr(img_part, "blob", b"")
                    if not img_bytes or len(img_bytes) < 100:
                        continue

                    ext = "png"
                    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
                    img_url = f"{self.base_storage_url}/{img_hash}.{ext}"

                    if img_hash not in seen_hashes:
                        seen_hashes.add(img_hash)
                        all_images.append({
                            "hash": img_hash,
                            "url": img_url,
                            "ext": ext,
                            "size_bytes": len(img_bytes),
                            "data": img_bytes,
                        })

                    caption = step_label or "Ảnh minh họa"
                    image_tags.append(f"![{caption}]({img_url})")

        except Exception as exc:
            logger.debug("Non-fatal error inspecting paragraph drawing: %s", exc)

        return image_tags

    def _extract_txbx_blocks(self, elem, doc) -> List[str]:
        """Extract paragraphs and tables from textboxes (w:txbxContent), skipping mc:Fallback to prevent duplicates."""
        blocks: List[str] = []
        try:
            import docx
            all_txbx = elem.xpath(".//*[local-name()='txbxContent']")
            valid_txbx = [tb for tb in all_txbx if not tb.xpath("ancestor::*[local-name()='Fallback']")]
            for tb in valid_txbx:
                for child in tb.iterchildren():
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag == "p":
                        try:
                            p_obj = docx.text.paragraph.Paragraph(child, doc)
                            formatted = self._format_paragraph(p_obj)
                            if formatted:
                                blocks.append(formatted)
                        except Exception:
                            t = "".join(child.itertext()).strip()
                            if t:
                                blocks.append(t)
                    elif tag == "tbl":
                        try:
                            t_obj = docx.table.Table(child, doc)
                            tbl_md = self._table_to_markdown(t_obj)
                            if tbl_md:
                                blocks.append(tbl_md)
                        except Exception:
                            pass
        except Exception as exc:
            logger.debug("Non-fatal error extracting textboxes: %s", exc)
        return blocks

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        try:
            import docx
        except ImportError as exc:
            raise DocumentParsingError("python-docx is required for DOCX parsing") from exc

        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            blocks: List[str] = []
            all_extracted_images: List[Dict[str, Any]] = []
            seen_image_hashes: Set[str] = set()

            # 0. Extract section headers (issuing agencies, bulletin dates, publication frequency)
            seen_headers: Set[str] = set()
            try:
                for sec in getattr(doc, "sections", []):
                    for hp in getattr(sec.header, "paragraphs", []):
                        txt = hp.text.strip()
                        if txt and txt not in seen_headers and len(txt) > 2:
                            seen_headers.add(txt)
                            blocks.append(txt)
                    for ht in getattr(sec.header, "tables", []):
                        tbl_md = self._table_to_markdown(ht)
                        if tbl_md and tbl_md not in seen_headers:
                            seen_headers.add(tbl_md)
                            blocks.append(tbl_md)
                    if getattr(sec, "different_first_page_header_footer", False):
                        first_hdr = getattr(sec, "first_page_header", None)
                        if first_hdr:
                            for hp in getattr(first_hdr, "paragraphs", []):
                                txt = hp.text.strip()
                                if txt and txt not in seen_headers and len(txt) > 2:
                                    seen_headers.add(txt)
                                    blocks.append(txt)
                            for ht in getattr(first_hdr, "tables", []):
                                tbl_md = self._table_to_markdown(ht)
                                if tbl_md and tbl_md not in seen_headers:
                                    seen_headers.add(tbl_md)
                                    blocks.append(tbl_md)
            except Exception as hdr_exc:
                logger.debug("Non-fatal error reading section headers: %s", hdr_exc)

            # 1. Iterate document body children in natural order (Paragraphs + Tables + Textboxes)
            try:
                body = doc.element.body
                for child in body.iterchildren():
                    if isinstance(child, docx.oxml.text.paragraph.CT_P):
                        p = docx.text.paragraph.Paragraph(child, doc)
                        formatted_p = self._format_paragraph(p)

                        # Determine if this paragraph represents a step (e.g. Bước 1, Bước 2...)
                        step_label = None
                        if formatted_p:
                            for prefix in ("bước", "step", "thao tác"):
                                if formatted_p.lower().startswith(prefix):
                                    step_label = formatted_p.split(":")[0].strip("#* ")
                                    break

                        img_tags = self._extract_images_from_paragraph(
                            p, doc, seen_image_hashes, all_extracted_images, step_label=step_label
                        )

                        if formatted_p:
                            blocks.append(formatted_p)

                        # Extract text boxes inside paragraph / drawing
                        for tb_block in self._extract_txbx_blocks(child, doc):
                            if tb_block and tb_block not in blocks:
                                blocks.append(tb_block)

                        # Anchor image tags immediately following paragraph text
                        for tag in img_tags:
                            blocks.append(tag)

                    elif isinstance(child, docx.oxml.table.CT_Tbl):
                        t = docx.table.Table(child, doc)
                        tbl_md = self._table_to_markdown(t)
                        if tbl_md:
                            blocks.append(tbl_md)
            except Exception as iter_exc:
                logger.debug("Falling back to paragraphs + tables sequential extraction: %s", iter_exc)
                for p in doc.paragraphs:
                    formatted_p = self._format_paragraph(p)
                    img_tags = self._extract_images_from_paragraph(
                        p, doc, seen_image_hashes, all_extracted_images
                    )
                    if formatted_p:
                        blocks.append(formatted_p)
                    for tb_block in self._extract_txbx_blocks(p._element, doc):
                        if tb_block and tb_block not in blocks:
                            blocks.append(tb_block)
                    for tag in img_tags:
                        blocks.append(tag)

                for t in doc.tables:
                    tbl_md = self._table_to_markdown(t)
                    if tbl_md:
                        blocks.append(tbl_md)

            # 2. Extract embedded OLE packages (word/embeddings/) if present in zip
            embedded_files_count = 0
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    for name in zf.namelist():
                        if name.startswith("word/embeddings/") and not name.endswith("/"):
                            emb_bytes = zf.read(name)
                            emb_filename = name.split("/")[-1]
                            if emb_filename.lower().endswith(".docx"):
                                sub_parser = DocxDocumentParser(base_storage_url=self.base_storage_url)
                                sub_doc = sub_parser.parse(emb_bytes, filename=f"{filename}::{emb_filename}")
                                for sp in sub_doc.pages:
                                    blocks.append(f"[Đính kèm: {emb_filename}]\n{sp.text}")
                                all_extracted_images.extend(sub_doc.metadata.get("images", []))
                                embedded_files_count += 1
            except Exception as zip_exc:
                logger.debug("No zip embeddings found: %s", zip_exc)

            # 3. Group into synthetic pages of ~500 words
            pages: List[ParsedPage] = []
            current_page_text: List[str] = []
            current_words = 0
            page_num = 1

            for b in blocks:
                current_page_text.append(b)
                current_words += len(b.split())
                if current_words >= 500:
                    pages.append(ParsedPage(page_number=page_num, text="\n\n".join(current_page_text)))
                    page_num += 1
                    current_page_text = []
                    current_words = 0

            if current_page_text:
                pages.append(ParsedPage(page_number=page_num, text="\n\n".join(current_page_text)))

            logger.info(
                "Parsed DOCX '%s': %d blocks across %d pages, %d images extracted & anchored, %d embedded files",
                filename, len(blocks), len(pages), len(all_extracted_images), embedded_files_count
            )
            return ParsedDocument(
                filename=filename,
                file_type="docx",
                pages=pages,
                metadata={
                    "total_pages": len(pages),
                    "total_blocks": len(blocks),
                    "images_count": len(all_extracted_images),
                    "images": all_extracted_images,
                    "embedded_files_count": embedded_files_count,
                },
            )
        except Exception as exc:
            logger.error("Failed to parse DOCX document '%s': %s", filename, exc)
            raise DocumentParsingError(f"DOCX parsing failed: {exc}") from exc
