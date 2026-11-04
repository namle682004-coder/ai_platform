"""
Support replies for turns that are not document questions.

Intent itself is decided by the LLM query analyzer (query_analyzer.py); this module only builds the
user-facing replies from the configured contact channels and reads session history (ticket ids,
the last unanswered question). Replies carry the hotline, remote-support method and ticket id in the
answer text itself, so every channel (web, Zalo, in-app) shows them without client changes.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Sequence

from .prompt_builder import REFUSAL_MESSAGE

TICKET_RE = re.compile(r"\b(ticket_[0-9a-f]{6,16})\b")
UNANSWERED_INTENTS = {"REFUSAL", "ESCALATION", "OUT_OF_SCOPE"}


def mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 7:
        return phone
    return f"{digits[:3]}****{digits[-3:]}"


def is_refusal_text(text: str) -> bool:
    return (text or "").strip().startswith(REFUSAL_MESSAGE[:40])


def last_ticket_in_history(history: Sequence[Dict[str, str]]) -> Optional[str]:
    for msg in reversed(list(history or [])):
        if msg.get("role") == "assistant":
            m = TICKET_RE.search(msg.get("content") or "")
            if m:
                return m.group(1)
    return None


def last_unanswered_question(history: Sequence[Dict[str, str]]) -> Optional[str]:
    """The most recent user question whose reply was a refusal / escalation."""
    msgs = list(history or [])
    for i in range(len(msgs) - 1, 0, -1):
        reply, question = msgs[i], msgs[i - 1]
        if reply.get("role") != "assistant" or question.get("role") != "user":
            continue
        intent = str(reply.get("intent") or "").upper()
        if intent in UNANSWERED_INTENTS or is_refusal_text(reply.get("content") or ""):
            return question.get("content") or None
    return None


class SupportResponder:
    """Builds support messages from the configured contact channels."""

    def __init__(self, hotline: str, support_method: str = "", instructions: str = "") -> None:
        self.hotline = (hotline or "").strip()
        self.support_method = (support_method or "").strip()
        self.instructions = (instructions or "").strip()

    def contact_line(self) -> str:
        parts = []
        if self.hotline:
            parts.append(f"gọi hotline **{self.hotline}**")
        if self.support_method:
            remote = f"hỗ trợ từ xa qua **{self.support_method}**"
            if self.instructions:
                remote += f" ({self.instructions.rstrip('.')})"
            parts.append(remote)
        return " hoặc ".join(parts) if parts else "liên hệ bộ phận hỗ trợ"

    @staticmethod
    def _outline_hint(titles: Sequence[str], outline: Sequence[str]) -> str:
        if not outline:
            return ""
        name = f" «{'», «'.join(titles)}»" if titles else ""
        return f"\n\nTài liệu hiện có{name} gồm các phần: {', '.join(outline)}. Bạn có thể hỏi về các nội dung này."

    def not_found(self, ticket_id: Optional[str], titles: Sequence[str] = (), outline: Sequence[str] = ()) -> str:
        lines = [REFUSAL_MESSAGE, ""]
        if ticket_id:
            lines.append(f"- Câu hỏi đã được ghi nhận và chuyển bộ phận phụ trách để bổ sung (mã yêu cầu: **{ticket_id}**).")
        lines.append(f"- Cần hỗ trợ ngay: {self.contact_line()}.")
        lines.append("- Nếu muốn được gọi lại, bạn có thể nhắn số điện thoại của mình tại đây.")
        return "\n".join(lines) + self._outline_hint(titles, outline)

    def identifier_not_found(self, code: str, scope: str, codes: Sequence[str]) -> str:
        if codes:
            return (
                f"Không có mã **{code}** trong tài liệu. Các mã thuộc nhóm **{scope}** hiện có: {', '.join(codes)}.\n\n"
                "Bạn có thể hỏi nội dung của một trong các mã trên."
            )
        return f"Không có mã **{code}** trong tài liệu, cũng không có mã nào thuộc nhóm **{scope}**."

    def handoff(self, ticket_id: Optional[str]) -> str:
        lines = []
        if self.hotline:
            lines.append(f"📞 **Hotline hỗ trợ: {self.hotline}**")
        if self.support_method:
            lines.append(f"💻 **Hỗ trợ từ xa: {self.support_method}**" + (f" – {self.instructions}" if self.instructions else ""))
        if not lines:
            lines.append("Vui lòng liên hệ bộ phận hỗ trợ.")
        lines.append("")
        if ticket_id:
            lines.append(f"Yêu cầu hỗ trợ của bạn đã được ghi nhận (mã: **{ticket_id}**).")
        lines.append("Nếu muốn kỹ thuật viên chủ động gọi lại, vui lòng nhắn số điện thoại của bạn.")
        return "\n".join(lines)

    def feedback(self, ticket_id: Optional[str], titles: Sequence[str] = (), outline: Sequence[str] = ()) -> str:
        msg = "Cảm ơn bạn đã phản hồi. Ý kiến của bạn đã được ghi nhận và chuyển quản trị viên"
        msg += f" (mã: **{ticket_id}**)." if ticket_id else "."
        msg += (
            "\n\nBạn có thể bấm 👍/👎 dưới mỗi câu trả lời để góp ý nhanh. Hãy cho biết cụ thể thông tin bạn cần "
            "(tên mục, mã, đối tượng áp dụng…), tôi sẽ tra cứu lại."
        )
        msg += self._outline_hint(titles, outline)
        msg += f"\n\nNếu muốn trao đổi trực tiếp với nhân viên hỗ trợ: {self.contact_line()}."
        return msg

    def contact_saved(self, phone: str, ticket_id: Optional[str], question: Optional[str]) -> str:
        msg = f"Đã ghi nhận số điện thoại **{mask_phone(phone)}**"
        if question:
            msg += f" cho câu hỏi «{question.strip()}»"
        if ticket_id:
            msg += f" (mã: **{ticket_id}**)"
        msg += ". Bộ phận phụ trách sẽ liên hệ lại với bạn."
        if self.hotline:
            msg += f" Nếu cần hỗ trợ gấp, vui lòng gọi hotline **{self.hotline}**."
        return msg

    def contact_declined(self) -> str:
        return (
            "Không sao, bạn không cần để lại số điện thoại. "
            f"Khi cần hỗ trợ, bạn có thể chủ động {self.contact_line()}."
        )

    def ticket_status(self, ticket_id: Optional[str], question: Optional[str]) -> str:
        if ticket_id:
            q = f" «{question.strip()}»" if question else ""
            return (
                f"Có. Câu hỏi{q} đã được ghi nhận và chuyển bộ phận phụ trách (mã yêu cầu: **{ticket_id}**). "
                f"Nếu cần hỗ trợ sớm hơn, bạn có thể {self.contact_line()}, hoặc nhắn số điện thoại để được gọi lại."
            )
        return (
            "Trong phiên này chưa có câu hỏi nào của bạn cần chuyển người phụ trách. "
            f"Nếu cần, hãy nhắn câu hỏi hoặc {self.contact_line()}."
        )

    def clarify(self, titles: Sequence[str], outline: Sequence[str]) -> str:
        msg = "Bạn muốn tra cứu cụ thể nội dung nào?"
        if outline:
            name = f" «{'», «'.join(titles)}»" if titles else ""
            msg += f" Tài liệu hiện có{name} gồm các phần: {', '.join(outline)}."
            examples = [f"«{h} gồm những nội dung gì?»" for h in list(outline)[:2]]
            msg += " Ví dụ, bạn có thể hỏi: " + ", ".join(examples) + "."
        msg += f"\n\nNếu cần trao đổi trực tiếp với nhân viên hỗ trợ: {self.contact_line()}."
        return msg

    def greeting(self) -> str:
        return "Xin chào! Tôi là trợ lý tra cứu tài liệu nội bộ. Bạn cần tra cứu nội dung gì?"

    def out_of_scope(self, category: str = "") -> str:
        about = f" ({category})" if category else ""
        return (
            f"Xin lỗi, yêu cầu này nằm ngoài phạm vi hỗ trợ{about} theo chính sách của hệ thống, nên tôi không thể cung cấp. "
            "Tôi hỗ trợ tra cứu nội dung, quy định trong các tài liệu nội bộ đã được nạp vào hệ thống — "
            "bạn hãy đặt câu hỏi về các nội dung đó."
        )
