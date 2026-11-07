"""
Tests for Support Configuration (Requirement #17).
Per-project hotline, remote support channel (UltraViewer), instructions, and security guards.
"""

import asyncio


from solutions.rag.application.components.conversation_policy import SupportResponder
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
from solutions.rag.infrastructure.repositories.mongo_support_repo import InMemorySupportRepository


def test_support_config_repo_save_and_get():
    repo = InMemorySupportRepository()

    async def _test():
        # Default is None
        cfg = await repo.get_support_config("tenant_dvkh")
        assert cfg is None

        # Save custom support channel
        saved = await repo.save_support_config(
            tenant_id="tenant_dvkh",
            hotline="1900 1234",
            support_method="UltraViewer",
            instructions="Cung cấp ID UltraViewer cho kỹ thuật viên; mật khẩu đọc qua điện thoại khi kết nối.",
        )
        assert saved["hotline"] == "1900 1234"
        assert saved["support_method"] == "UltraViewer"
        assert "ID UltraViewer" in saved["instructions"]

        # Retrieve
        fetched = await repo.get_support_config("tenant_dvkh")
        assert fetched is not None
        assert fetched["hotline"] == "1900 1234"

    asyncio.run(_test())


def test_chat_use_case_uses_tenant_specific_support_config():
    repo = InMemorySupportRepository()

    async def _test():
        await repo.save_support_config(
            tenant_id="tenant_qldv",
            hotline="0262 999 888",
            support_method="UltraViewer",
            instructions="Chỉ cung cấp ID, mật khẩu đọc qua điện thoại.",
        )

        uc = RagChatUseCase.__new__(RagChatUseCase)
        uc.support_repo = repo
        uc.support = SupportResponder(hotline="", support_method="", instructions="")

        responder_qldv = await uc._support_for_tenant("tenant_qldv")
        assert responder_qldv.hotline == "0262 999 888"
        assert responder_qldv.support_method == "UltraViewer"
        assert "0262 999 888" in responder_qldv.contact_line()

        # Other tenant falls back to default
        responder_other = await uc._support_for_tenant("tenant_other")
        assert responder_other.hotline == ""
        assert "liên hệ bộ phận hỗ trợ" in responder_other.contact_line()

    asyncio.run(_test())
