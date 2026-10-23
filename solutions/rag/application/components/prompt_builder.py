"""
Enterprise Grounded Context & Prompt Assembler for AIP RAG.
Builds strictly grounded system prompts, citation footnotes, and refusal templates.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

REFUSAL_MESSAGE = (
    "Thông tin về vấn đề này không có trong tài liệu nội bộ được cung cấp. "
    "Vui lòng liên hệ bộ phận liên quan để được giải đáp chính xác."
)

FEW_SHOT_CITATION_EXAMPLE = (
    "--- QUY TẮC ĐỊNH DẠNG TRÍCH DẪN NGUỒN (Citation Discipline) ---\n"
    "1. Gắn số trích dẫn nguồn [1], [2] ở cuối mỗi mệnh đề khẳng định dữ kiện.\n"
    "2. CHỈ sử dụng thông tin có thật trong TÀI LIỆU NỘI BỘ THAM KHẢO dưới đây, TUYỆT ĐỐI không bịa đặt hoặc dùng kiến thức ngoài.\n"
    "----------------------------------------------------------------"
)

CHITCHAT_SYSTEM_PROMPT = (
    "Bạn là trợ lý AI thông minh, thân thiện và lịch sự của nền tảng Enterprise AI.\n"
    "Nhiệm vụ: Trả lời người dùng một cách tự nhiên, ngắn gọn và hữu ích bằng tiếng Việt.\n"
    "Lưu ý: Bạn là trợ lý ảo, không phải con người, hãy phản hồi khéo léo và phù hợp khi được hỏi về các hoạt động đời thường."
)


class RagPromptBuilder:
    """Builds grounded context blocks and structured prompt templates for LLM generation (Stuff, Map-Reduce, Refine)."""

    @staticmethod
    def prune_context_noise(text: str, query: str = "", max_chars: int = 2500) -> str:
        """
        Extractive context pruning for large parent chunks.
        Preserves Markdown/HTML tables completely.
        For long narrative text, removes disconnected sentences while
        preserving query-relevant sentences and their immediate surrounding clauses.
        """
        if not text or len(text) <= max_chars:
            return text
        # If it's predominantly a table, preserve intact
        if "<table" in text.lower() or text.count("|") >= 6:
            return text

        import re
        sentences = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", text) if s.strip()]
        if len(sentences) <= 4:
            return text

        q_terms = [w.lower() for w in re.findall(r"\w+", query) if len(w) >= 2]
        if not q_terms:
            return text[:max_chars]

        scored_sents = []
        for i, s in enumerate(sentences):
            s_lower = s.lower()
            overlap = sum(1 for t in q_terms if t in s_lower)
            has_num = any(ch.isdigit() for ch in s)
            score = overlap * 2 + (1 if has_num else 0)
            scored_sents.append((i, s, score))

        selected_indices = set()
        for i, s, score in sorted(scored_sents, key=lambda x: x[2], reverse=True)[:8]:
            if score > 0:
                selected_indices.add(i)
                if i > 0:
                    selected_indices.add(i - 1)
                if i < len(sentences) - 1:
                    selected_indices.add(i + 1)

        if not selected_indices:
            return text[:max_chars]

        pruned = [sentences[i] for i in sorted(selected_indices)]
        res = " ".join(pruned)
        return res[:max_chars]

    @staticmethod
    def linearize_compact_tables(text: str) -> str:
        """
        Converts small 1-2 row Markdown tables into unambiguous Key-Value pairs (Table Linearization),
        preventing 1D causal LLMs from confusing adjacent columns in horizontal tabular layouts.
        Preserves larger multi-row tables intact.
        """
        if "|" not in text:
            return text

        lines = [line.rstrip() for line in text.split("\n")]
        table_lines: List[str] = []
        result_lines: List[str] = []

        def flush_table(t_lines: List[str]) -> List[str]:
            if not t_lines or len(t_lines) < 3:
                return t_lines
            delim_line = t_lines[1].strip()
            if not (delim_line.startswith("|") and all(c in "|:- \t" for c in delim_line)):
                return t_lines
            header_cells = [c.strip() for c in t_lines[0].strip("|").split("|")]
            data_rows = t_lines[2:]
            if 1 <= len(data_rows) <= 2:
                linearized = []
                for r in data_rows:
                    row_cells = [c.strip() for c in r.strip("|").split("|")]
                    for h, v in zip(header_cells, row_cells):
                        if h and v:
                            linearized.append(f"- {h}: {v}")
                if linearized:
                    return linearized
            return t_lines

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                table_lines.append(stripped)
            else:
                if table_lines:
                    result_lines.extend(flush_table(table_lines))
                    table_lines = []
                result_lines.append(line)

        if table_lines:
            result_lines.extend(flush_table(table_lines))

        return "\n".join(result_lines)

    def extract_citations_and_blocks(
        self,
        top_chunks: List[Any],
        query: str = "",
        use_parent_context: bool = False,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Extracts structured citation dicts and grounded context blocks from chunks,
        resolving hierarchical parent-child context if available and pruning noise.
        """
        citations: List[Dict[str, Any]] = []
        context_blocks: List[str] = []
        seen_parents: set = set()

        for idx, chunk in enumerate(top_chunks, start=1):
            raw_text = (getattr(chunk, "text", "") or "").strip()
            chunk_meta = getattr(chunk, "metadata", {}) or {}
            parent_id = chunk_meta.get("parent_id")
            parent_text = chunk_meta.get("parent_text")

            # Excerpt for citation chip: concise child snippet
            if len(raw_text) <= 300:
                excerpt = raw_text
            else:
                truncated = raw_text[:300]
                last_space = truncated.rfind(" ")
                excerpt = (truncated[:last_space] if last_space > 0 else truncated) + "..."

            chunk_id = chunk_meta.get("chunk_id", f"{getattr(chunk, 'doc_id', '')}_{getattr(chunk, 'chunk_index', 0)}")
            heading = chunk_meta.get("heading") or chunk_meta.get("heading_path") or ""
            content_type = chunk_meta.get("content_type", "text")

            citations.append({
                "index": idx,
                "doc_id": getattr(chunk, "doc_id", ""),
                "chunk_id": chunk_id,
                "parent_id": parent_id,
                "title": getattr(chunk, "title", "Tài liệu"),
                "heading": heading,
                "page_number": getattr(chunk, "page_number", 1),
                "content_type": content_type,
                "score": round(float(getattr(chunk, "score", 0.0)), 4),
                "excerpt": excerpt,
                "text": raw_text,
            })
            heading_info = f", Mục: {heading}" if heading else ""

            text_for_context = raw_text
            if use_parent_context and parent_text:
                if parent_id and parent_id in seen_parents:
                    continue
                if parent_id:
                    seen_parents.add(parent_id)
                text_for_context = self.prune_context_noise(parent_text, query=query)

            text_for_context = self.linearize_compact_tables(text_for_context)

            context_blocks.append(
                f"[{idx}] (Tài liệu: {getattr(chunk, 'title', 'Tài liệu')}, Trang: {getattr(chunk, 'page_number', 1)}{heading_info})\n{text_for_context}"
            )

        return citations, context_blocks

    @staticmethod
    def reorder_lost_in_middle(chunks: List[Any]) -> List[Any]:
        """
        Reorders chunks according to the Lost-in-the-Middle U-shaped attention principle (Slide 92 / Liu et al.).
        Places highest-score chunk (Rank 1) at the start (index 0),
        second highest-score chunk (Rank 2) at the end (index -1),
        and remaining chunks in the middle.
        """
        if len(chunks) <= 2:
            return list(chunks)
        left = [chunks[i] for i in range(0, len(chunks), 2)]
        right = [chunks[i] for i in range(1, len(chunks), 2)]
        return left + right[::-1]

    def build_context_and_citations(
        self,
        top_chunks: List[Any],
        query: str = "",
        use_parent_context: bool = False,
        glossary: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Transforms retrieved and reranked chunks into structured citation dicts
        and a consolidated grounding reference context block (Stuff Strategy - Slide 80).
        Applies Lost-in-the-Middle U-shaped attention ordering and Quote-First discipline.
        """
        citations, context_blocks = self.extract_citations_and_blocks(
            top_chunks,
            query=query,
            use_parent_context=use_parent_context,
        )
        context_str = "\n\n".join(context_blocks)
        if glossary:
            from .acronym_harvester import glossary_for_prompt
            glossary_block = glossary_for_prompt(glossary, query=query, chunks_text=context_str)
            if glossary_block:
                context_str = f"{glossary_block}\n\n{context_str}"
        system_prompt = (
            "Bạn là trợ lý AI chuyên nghiệp của nền tảng AIP.\n"
            "Nhiệm vụ của bạn là trả lời câu hỏi của người dùng dựa HOÀN TOÀN và CHÍNH XÁC vào các đoạn tài liệu tham khảo được cung cấp dưới đây.\n\n"
            "QUY TẮC NGÔN NGỮ BẮT BUỘC: Bạn BẮT BUỘC phải sinh câu trả lời HOÀN TOÀN BẰNG TIẾNG VIỆT theo đúng ngôn ngữ của câu hỏi và tài liệu tham khảo. Tuyệt đối không dịch hoặc trả lời bằng tiếng Anh.\n\n"
            "--- NGUYÊN TẮC XỬ LÝ DỮ LIỆU & SINH CÂU TRẢ LỜI ---\n"
            "1. KỶ LUẬT TRÍCH DẪN NGUỒN (Kỷ luật Quote-First):\n"
            "   - Với mỗi câu hoặc mệnh đề khẳng định dữ kiện, bắt buộc trích dẫn bằng chứng cụ thể và gắn ký hiệu nguồn tương ứng [1], [2] ở cuối câu.\n"
            "   - Chỉ trích dẫn các tài liệu thực sự cung cấp thông tin được sử dụng. Không trích dẫn tài liệu không liên quan.\n\n"
            "2. ĐỐI CHIẾU THỰC THỂ TUYỆT ĐỐI (ENTITY GROUNDING) & RÀNG BUỘC PHÂN CẤP:\n"
            "   - ĐỐI CHIẾU TIÊU ĐỀ TÀI LIỆU VỚI ĐỐI TƯỢNG ĐƯỢC HỎI:\n"
            "     Khi câu hỏi yêu cầu thông tin về một chủ thể, vị trí hoặc đối tượng cụ thể:\n"
            "     BẮT BUỘC bạn CHỈ ĐƯỢC trích xuất thông tin từ đoạn tài liệu có tiêu đề `Tài liệu:` khớp với đối tượng đó.\n"
            "     TUYỆT ĐỐI KHÔNG trích xuất hoặc lấy nhầm thông tin từ tài liệu của đối tượng khác dù cấu trúc văn bản hoặc số thứ tự các mục giống nhau.\n"
            "   - QUY TẮC CÁCH LY HỘI THOẠI ĐA LƯỢT (MULTI-TURN INDEPENDENCE):\n"
            "     Mỗi câu hỏi về một đối tượng phải được trả lời HOÀN TOÀN ĐỘC LẬP dựa trên đúng tài liệu của đối tượng đó.\n"
            "     TUYỆT ĐỐI KHÔNG mang dữ kiện của đối tượng ở câu hỏi trước gán ghép sang đối tượng của câu hỏi hiện tại.\n"
            "   - KHI ĐƯỢC HỎI VỀ MỤC CON ĐÁNH SỐ HOẶC ĐIỀU KHOẢN (Ví dụ: 'mục 2.1', 'điều 3', 'mục 4.1'):\n"
            "     BẮT BUỘC phải tìm đúng dòng/vị trí mang chính xác số hiệu đó và trích xuất TOÀN BỘ nội dung chi tiết của đúng mục đó. Tuyệt đối không lấy nhầm mục khác.\n"
            "   - KHI ĐƯỢC HỎI VỀ MỤC ĐỀ / CHỦ ĐỀ CỤ THỂ:\n"
            "     BẮT BUỘC trích xuất từ đoạn tài liệu có tiêu đề `Mục:` tương ứng với chủ đề được hỏi, không lấy nhầm từ các mục khác.\n"
            "   - Khi câu hỏi yêu cầu so sánh giữa hai hay nhiều đối tượng: Bắt buộc trình bày rõ ràng từng đối tượng theo đúng tài liệu tương ứng, không được lẫn lộn tiêu chuẩn giữa các đối tượng.\n\n"
            "3. BẢO TOÀN TÍNH CHÍNH XÁC CỦA DỮ LIỆU CẤU TRÚC VÀ BẢNG BIỂU:\n"
            "   - Khi đọc dữ liệu bảng biểu: BẮT BUỘC phải đọc theo hàng và cột tương ứng, phân biệt chính xác từng trường thông tin.\n"
            "   - Đối chiếu đúng tên trường/tiêu đề cột với câu hỏi. Tuyệt đối không đảo lộn giá trị giữa các trường thông tin hoặc giữa các đối tượng khác nhau trong cùng một bảng.\n"
            "   - BẮT BUỘC liệt kê đầy đủ và chính xác tất cả các nội dung theo đúng trường thông tin được hỏi.\n\n"
            "4. XỬ LÝ LINH HOẠT CÂU HỎI VẮN TẮT (GREY-ZONE) & QUY TẮC CHỐNG SUY DIỄN PHỦ ĐỊNH:\n"
            "   - Khi câu hỏi của người dùng ngắn gọn, hỏi khái quát, dùng từ đồng nghĩa, từ viết tắt hoặc không trùng khớp 100% từng từ với tiêu đề trong tài liệu:\n"
            "     BẮT BUỘC phải đọc kỹ nội dung tài liệu tham khảo để tổng hợp câu trả lời hữu ích nhất, tóm tắt rõ ràng các quy định, nội dung, phạm vi công việc hay tiêu chí có trong tài liệu (kèm trích dẫn nguồn [1], [2]). Tuyệt đối KHÔNG được từ chối trả lời nếu tài liệu có đề cập đến đối tượng hoặc nội dung liên quan.\n"
            "   - QUY TẮC CHỐNG SUY DIỄN PHỦ ĐỊNH: Khi câu hỏi hỏi về sự tồn tại của một ngành nghề, dịch vụ, quy định hoặc đối tượng cụ thể mà tài liệu tham khảo HOÀN TOÀN KHÔNG đề cập tới: TUYỆT ĐỐI KHÔNG tự suy diễn để khẳng định 'Không có' hay 'Không đào tạo'. Bạn BẮT BUỘC phải trả lời chính xác câu từ chối chuẩn:\n"
            "   - Tuyệt đối không tự suy diễn, không ước lượng số liệu và không bổ sung kiến thức nằm ngoài tài liệu tham khảo.\n\n"
            "5. ĐỊNH DẠNG CHECKLIST TỪNG BƯỚC CHUẨN MỰC (GEN-RAG-01 - CHO HƯỚNG DẪN THAO TÁC, CÀI ĐẶT, XỬ LÝ SỰ CỐ):\n"
            "   - Đối với câu hỏi về hướng dẫn thao tác, cài đặt, hoặc xử lý sự cố / lỗi, BẮT BUỘC định dạng câu trả lời theo cấu trúc Checklist từng bước:\n"
            "     ### HƯỚNG DẪN XỬ LÝ [TÊN THAO TÁC / SỰ CỐ]\n"
            "     * **Bước 1: [Tên thao tác]**\n"
            "       - Chi tiết: [Hướng dẫn cụ thể các nút cần bấm, menu cần chọn hoặc quy định cụ thể]\n"
            "       ![Ảnh minh họa Bước 1](url_anh_1) (nếu trong tài liệu có ảnh minh họa tương ứng)\n"
            "     * **Bước 2: [Tên thao tác tiếp theo]**\n"
            "       - Chi tiết: [...]\n"
            "     ...\n"
            "     > [!IMPORTANT] LƯU Ý QUAN TRỌNG: [Quy định bắt buộc hoặc cảnh báo rủi ro nếu có]\n\n"
            "     **Căn cứ pháp lý & Tài liệu tham chiếu:**\n"
            "     - [1] [Tên tài liệu / Văn bản] (Mục ..., Trang ...)\n"
            "   - ĐỒNG BỘ THẺ ẢNH MINH HỌA (TEXT-IMAGE ALIGNMENT): Nếu tài liệu tham khảo có thẻ ảnh dạng `![...](url)`, BẮT BUỘC phải giữ nguyên thẻ ảnh và đặt ngay dưới câu mô tả bước thao tác tương ứng, tuyệt đối không di chuyển thẻ ảnh lên trước câu hướng dẫn và không làm mất thẻ ảnh.\n\n"
            "6. ĐỊNH DẠNG CHUNG: Trình bày rõ ràng, mạch lạc, dùng tiếng Việt chuẩn mực.\n\n"
            f"{FEW_SHOT_CITATION_EXAMPLE}\n\n"
            f"--- TÀI LIỆU NỘI BỘ THAM KHẢO ---\n{context_str}\n---------------------------------\n"
            "Hãy đọc kỹ các đoạn tài liệu trên và trả lời câu hỏi của người dùng hoàn toàn bằng TIẾNG VIỆT:"
        )
        return citations, system_prompt

    def build_map_prompt(self, chunk: Any, query: str, chunk_index: int) -> List[Dict[str, str]]:
        """
        Builds messages for the Map phase of Map-Reduce Combine Strategy (Slide 80).
        Extracts relevant facts and figures from a single chunk with citation footnote.
        """
        raw_text = (getattr(chunk, "text", "") or "").strip()
        chunk_meta = getattr(chunk, "metadata", {}) or {}
        parent_text = chunk_meta.get("parent_text")
        text_to_use = parent_text if parent_text else raw_text
        title = getattr(chunk, "title", "Tài liệu")
        page_number = getattr(chunk, "page_number", 1)
        heading = chunk_meta.get("heading") or chunk_meta.get("heading_path") or ""
        heading_info = f", Mục: {heading}" if heading else ""

        system_prompt = (
            "Bạn là chuyên gia phân tích và trích xuất dữ kiện của nền tảng AIP.\n"
            f"Nhiệm vụ: Đọc kỹ ĐOẠN TÀI LIỆU [{chunk_index}] dưới đây và trích xuất TOÀN BỘ các thông tin, dữ kiện, số liệu, quy định liên quan trực tiếp đến câu hỏi của người dùng.\n"
            "Quy tắc bắt buộc:\n"
            f"1. Đoạn tài liệu này có chỉ số trích dẫn là [{chunk_index}]. Luôn gắn kèm ký hiệu [{chunk_index}] vào cuối mỗi thông tin được trích xuất.\n"
            "2. Giữ nguyên tính chính xác của số liệu, điều khoản, bảng biểu gốc.\n"
            "3. Nếu đoạn tài liệu KHÔNG chứa bất kỳ thông tin nào liên quan đến câu hỏi, CHỈ TRẢ VỀ DUY NHẤT một dòng: 'KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN'."
        )

        user_content = (
            f"--- ĐOẠN TÀI LIỆU [{chunk_index}] ---\n"
            f"Tài liệu: {title}, Trang: {page_number}{heading_info}\n"
            f"Nội dung:\n{text_to_use}\n"
            "------------------------------------\n"
            f"Câu hỏi: {query}\n\n"
            f"Các dữ kiện liên quan trích xuất từ đoạn [{chunk_index}]:"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def build_reduce_prompt(
        self,
        query: str,
        map_summaries: List[str],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """
        Builds messages for the Reduce phase of Map-Reduce Combine Strategy (Slide 80).
        Synthesizes all mapped chunk extractions into a final comprehensive answer.
        """
        combined_summaries = "\n\n".join(map_summaries)
        system_prompt = (
            "Bạn là trợ lý AI chuyên nghiệp của nền tảng AIP.\n"
            "Nhiệm vụ: Dưới đây là các thông tin và dữ kiện đã được trích xuất từ các tài liệu nội bộ khác nhau.\n"
            "Hãy tổng hợp các dữ kiện này thành một câu trả lời hoàn chỉnh, mạch lạc, chính xác và có chiều sâu cho câu hỏi của người dùng.\n\n"
            "Nguyên tắc bắt buộc:\n"
            "1. Luôn bảo toàn và ghim các ký hiệu trích dẫn [1], [2], [3]... ở cuối mỗi câu hoặc thông tin khẳng định.\n"
            "2. Trình bày khoa học: Sử dụng danh sách gạch đầu dòng hoặc bảng Markdown (| Cột 1 | Cột 2 |) nếu có số liệu so sánh.\n"
            "3. Tuyệt đối không tự ý bịa đặt hoặc suy diễn thông tin nằm ngoài các dữ kiện được cung cấp.\n"
            "4. Trả lời bằng tiếng Việt chuẩn mực, rõ ràng.\n"
            "5. Nếu câu hỏi là hướng dẫn thao tác, cài đặt, hoặc xử lý sự cố, bắt buộc trình bày dạng Checklist từng bước (* **Bước X: ...**), kèm thẻ ảnh minh họa ngay dưới câu mô tả bước tương ứng nếu có.\n\n"
            f"{FEW_SHOT_CITATION_EXAMPLE}"
        )

        user_content = (
            "--- CÁC DỮ KIỆN TRÍCH XUẤT TỪ CÁC TÀI LIỆU ---\n"
            f"{combined_summaries}\n"
            "--------------------------------------------------\n"
            f"Câu hỏi của người dùng: {query}\n\n"
            "Câu trả lời tổng hợp hoàn chỉnh:"
        )

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        return messages

    def build_refine_initial_prompt(
        self,
        chunk: Any,
        query: str,
        chunk_index: int = 1,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """
        Builds initial prompt for the Refine Combine Strategy (Slide 80) on chunk 1.
        """
        raw_text = (getattr(chunk, "text", "") or "").strip()
        chunk_meta = getattr(chunk, "metadata", {}) or {}
        parent_text = chunk_meta.get("parent_text")
        text_to_use = parent_text if parent_text else raw_text
        title = getattr(chunk, "title", "Tài liệu")
        page_number = getattr(chunk, "page_number", 1)
        heading = chunk_meta.get("heading") or chunk_meta.get("heading_path") or ""
        heading_info = f", Mục: {heading}" if heading else ""

        system_prompt = (
            "Bạn là trợ lý AI chuyên nghiệp của nền tảng AIP.\n"
            f"Hãy trả lời câu hỏi của người dùng CHÍNH XÁC dựa vào ĐOẠN TÀI LIỆU [{chunk_index}] dưới đây.\n\n"
            "Nguyên tắc:\n"
            f"1. Luôn gắn ký hiệu trích dẫn [{chunk_index}] ở đuôi mỗi câu hoặc thông tin được tham chiếu.\n"
            "2. Không tự ý bịa đặt hoặc suy diễn ngoài tài liệu.\n"
            "3. Trình bày rõ ràng bằng tiếng Việt.\n\n"
            f"{FEW_SHOT_CITATION_EXAMPLE}"
        )

        user_content = (
            f"--- ĐOẠN TÀI LIỆU [{chunk_index}] ---\n"
            f"Tài liệu: {title}, Trang: {page_number}{heading_info}\n"
            f"Nội dung:\n{text_to_use}\n"
            "------------------------------------\n"
            f"Câu hỏi: {query}\n\n"
            f"Câu trả lời ban đầu dựa trên đoạn [{chunk_index}]:"
        )

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        return messages

    def build_refine_step_prompt(
        self,
        existing_answer: str,
        next_chunk: Any,
        query: str,
        chunk_index: int,
    ) -> List[Dict[str, str]]:
        """
        Builds iterative refinement prompt for the Refine Combine Strategy (Slide 80) for subsequent chunks.
        """
        raw_text = (getattr(next_chunk, "text", "") or "").strip()
        chunk_meta = getattr(next_chunk, "metadata", {}) or {}
        parent_text = chunk_meta.get("parent_text")
        text_to_use = parent_text if parent_text else raw_text
        title = getattr(next_chunk, "title", "Tài liệu")
        page_number = getattr(next_chunk, "page_number", 1)
        heading = chunk_meta.get("heading") or chunk_meta.get("heading_path") or ""
        heading_info = f", Mục: {heading}" if heading else ""

        system_prompt = (
            "Bạn là trợ lý AI chuyên nghiệp của nền tảng AIP.\n"
            "Chúng ta đã có một câu trả lời dựa trên các tài liệu đã đọc trước đó. "
            f"Nhiệm vụ của bạn là đọc ĐOẠN TÀI LIỆU TIẾP THEO [{chunk_index}] dưới đây và TINH CHỈNH/BỔ SUNG vào câu trả lời hiện tại nếu tài liệu mới có dữ kiện liên quan.\n"
            "Nguyên tắc bắt buộc:\n"
            "1. Nếu tài liệu mới KHÔNG có thêm thông tin mới hoặc không liên quan, hãy GIỮ NGUYÊN câu trả lời hiện tại mà không thay đổi.\n"
            f"2. Nếu tài liệu mới có thêm điều khoản, số liệu, quy định mới, hãy tích hợp mượt mà và gắn kèm ký hiệu [{chunk_index}].\n"
            "3. Tuyệt đối không làm mất các ký hiệu trích dẫn cũ ([1], [2]...) từ các tài liệu trước.\n"
            "4. Giữ câu trả lời mạch lạc, chuẩn xác bằng tiếng Việt."
        )

        user_content = (
            f"Câu hỏi: {query}\n\n"
            f"--- CÂU TRẢ LỜI HIỆN TẠI ---\n{existing_answer}\n"
            "----------------------------\n\n"
            f"--- ĐOẠN TÀI LIỆU MỚI [{chunk_index}] ---\n"
            f"Tài liệu: {title}, Trang: {page_number}{heading_info}\n"
            f"Nội dung:\n{text_to_use}\n"
            "----------------------------------------\n\n"
            "Hãy cập nhật và tinh chỉnh câu trả lời (hoặc giữ nguyên nếu không có ý mới):"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def build_map_rerank_prompt(
        self,
        chunk: Any,
        query: str,
        chunk_index: int,
    ) -> List[Dict[str, str]]:
        """
        Builds messages for the Map-Rerank Combine Strategy (Slide 80).
        Instructs LLM to answer the query solely using the provided chunk and assign a confidence score (0-100).
        Used when high precision and noise rejection across similar documents are required.
        """
        raw_text = (getattr(chunk, "text", "") or "").strip()
        chunk_meta = getattr(chunk, "metadata", {}) or {}
        parent_text = chunk_meta.get("parent_text")
        text_to_use = parent_text if parent_text else raw_text
        title = getattr(chunk, "title", "Tài liệu")
        page_number = getattr(chunk, "page_number", 1)
        heading = chunk_meta.get("heading") or chunk_meta.get("heading_path") or ""
        heading_info = f", Mục: {heading}" if heading else ""

        system_prompt = (
            "Bạn là chuyên gia phân tích và đánh giá tài liệu của nền tảng AIP.\n"
            f"Nhiệm vụ: Đọc kỹ ĐOẠN TÀI LIỆU [{chunk_index}] và trả lời câu hỏi của người dùng CHỈ DỰA VÀO đoạn tài liệu này.\n"
            "Đồng thời, bạn BẮT BUỘC phải chấm ĐIỂM TỰ TIN (từ 0 đến 100) thể hiện mức độ đoạn tài liệu này trả lời câu hỏi:\n"
            "- 90-100: Đoạn tài liệu trả lời trực tiếp, đầy đủ và chính xác câu hỏi.\n"
            "- 50-89: Đoạn tài liệu có liên quan một phần nhưng câu trả lời chưa trọn vẹn.\n"
            "- 0: Đoạn tài liệu hoàn toàn không chứa thông tin hoặc câu trả lời cho câu hỏi.\n\n"
            "ĐỊNH DẠNG ĐẦU RA BẮT BUỘC:\n"
            "ĐIỂM: <số nguyên từ 0 đến 100>\n"
            f"CÂU_TRẢ_LỜI: <Nội dung câu trả lời, ghim kèm ký hiệu [{chunk_index}] ở đuôi câu khẳng định. Nếu điểm 0, ghi 'KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN'>\n\n"
            f"{FEW_SHOT_CITATION_EXAMPLE}"
        )

        user_content = (
            f"--- ĐOẠN TÀI LIỆU [{chunk_index}] ---\n"
            f"Tài liệu: {title}, Trang: {page_number}{heading_info}\n"
            f"Nội dung:\n{text_to_use}\n"
            "------------------------------------\n"
            f"Câu hỏi: {query}\n\n"
            "Đánh giá và câu trả lời:"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def build_multihop_cot_prompt(
        self,
        query: str,
        sub_queries: List[str],
        hop1_blocks: List[str],
        hop2_blocks: List[str],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """
        Builds messages for Multi-Hop Reasoning & Iterative RAG (Slide 94-103).
        Guides the LLM through a Chain-of-Thought (CoT) synthesis over multi-hop facts.
        """
        q1 = sub_queries[0] if len(sub_queries) > 0 else "Bước 1"
        q2 = sub_queries[1] if len(sub_queries) > 1 else "Bước 2"

        hop1_text = "\n\n".join(hop1_blocks) if hop1_blocks else "Không tìm thấy dữ kiện bổ sung trong bước này."
        hop2_text = "\n\n".join(hop2_blocks) if hop2_blocks else "Không tìm thấy dữ kiện bổ sung trong bước này."

        is_comparative = any(w in query.lower() for w in ["so sánh", "khác biệt", "đối chiếu", "compare", "giống và khác"])
        if is_comparative:
            instruction = (
                "HƯỚNG DẪN TRẢ LỜI CÂU HỎI SO SÁNH / ĐỐI CHIẾU:\n"
                "1. Trình bày trực diện BẢNG SO SÁNH Markdown rõ ràng giữa các thực thể theo đúng tiêu chí được hỏi:\n"
                "   | Tiêu chí | [Thực thể 1] | [Thực thể 2] |\n"
                "2. Liệt kê đầy đủ, chính xác mọi số liệu, số năm công tác, cấp bậc chức vụ hoặc đối tượng cụ thể từ tài liệu (ví dụ: số năm công tác, chức danh, viên chức, người lao động...).\n"
                "3. Sau bảng, nêu kết luận tóm tắt ngắn gọn trong 2-3 câu.\n"
                "4. Luôn ghim ký hiệu trích dẫn [1], [2] ở đuôi thông tin.\n"
                "5. Tuyệt đối không bịa đặt hoặc suy diễn ngoài tài liệu."
            )
            user_prompt_suffix = "Hãy lập bảng so sánh đối chiếu trực diện và đưa ra câu trả lời chính xác:"
        else:
            instruction = (
                "HƯỚNG DẪN TRẢ LỜI (Chain-of-Thought):\n"
                f"1. Phân tích và kết nối các dữ kiện từ các bước để trả lời câu hỏi tổng thể: '{query}'.\n"
                "2. BẮT BUỘC ghim ký hiệu trích dẫn [1], [2]... ở đuôi mỗi câu hoặc ý khẳng định tương ứng.\n"
                "3. Tuyệt đối không tự ý bịa đặt hoặc suy diễn thông tin nằm ngoài các dữ kiện được cung cấp."
            )
            user_prompt_suffix = "Hãy suy luận từng bước và đưa ra câu trả lời tổng hợp chính xác:"

        system_prompt = (
            "Bạn là trợ lý AI chuyên nghiệp của nền tảng AIP.\n"
            "Nhiệm vụ của bạn là giải quyết câu hỏi phức hợp của người dùng thông qua suy luận đa bước (Multi-Hop Reasoning - Chain-of-Thought).\n"
            "Dưới đây là các dữ kiện thu thập được qua các bước tìm kiếm:\n\n"
            f"--- DỮ KIỆN BƯỚC 1 (Truy vấn: '{q1}') ---\n"
            f"{hop1_text}\n\n"
            f"--- DỮ KIỆN BƯỚC 2 (Truy vấn: '{q2}') ---\n"
            f"{hop2_text}\n"
            "--------------------------------------------------\n\n"
            f"{instruction}\n\n"
            f"{FEW_SHOT_CITATION_EXAMPLE}"
        )

        user_content = (
            f"Câu hỏi của người dùng: {query}\n\n"
            f"{user_prompt_suffix}"
        )

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        return messages


prompt_builder = RagPromptBuilder()
