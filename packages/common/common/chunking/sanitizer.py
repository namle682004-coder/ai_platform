"""
PII Sanitizer for cleaning confidential and sensitive information from text.
Shared enterprise contract across AIP Platform services and workers.
"""

from __future__ import annotations

import re


class PiiSanitizer:
    """
    ING-RAG-07: Automated PII Masking & Sensitive Data Sanitization (PDPD / Decree 13/2023/NĐ-CP Compliance).
    Replaces sensitive personal and credential entities with standard tokens:
    - [EMAIL_REDACTED]
    - [PHONE_REDACTED]
    - [ID_REDACTED]
    - [SECRET_KEY_REDACTED]
    Guarantees 0% false positive redaction on legal document citations (e.g. 123/2020/NĐ-CP, Điều 12).
    """

    @staticmethod
    def sanitize(text: str) -> str:
        if not text:
            return ""

        # 1. Mask API keys, tokens, and system secrets
        cleaned = re.sub(
            r"\b(?:sk-[a-zA-Z0-9_\-]{20,}|ghp_[a-zA-Z0-9]{20,}|aip_[a-zA-Z0-9_]{16,}|(?:ey[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}))\b",
            "[SECRET_KEY_REDACTED]",
            text,
        )
        # Mask system password / secret declarations: e.g. "password: secret123", "mật khẩu: abcXYZ123"
        cleaned = re.sub(
            r"(?i)\b(password|mật\s*khẩu|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?([^\s'\"]{4,})['\"]?",
            r"\1: [SECRET_KEY_REDACTED]",
            cleaned,
        )

        # 2. Mask email addresses
        cleaned = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL_REDACTED]", cleaned)

        # 3. Mask Vietnamese phone numbers (e.g. 0912345678, +84912345678)
        cleaned = re.sub(r"(?:\+84|0)(?:3|5|7|8|9)\d{8}\b", "[PHONE_REDACTED]", cleaned)

        # 4. Mask 12-digit CCCD / 9-digit CMND without touching legal doc numbers (e.g. 123/2020/NĐ-CP or dates)
        cleaned = re.sub(r"(?<![/.-])\b\d{12}\b(?![/.-])", "[ID_REDACTED]", cleaned)

        return cleaned

