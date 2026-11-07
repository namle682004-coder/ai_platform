"""
Support replies must not show placeholder contact details or ask users for remote-access credentials
unless a deployment configures its real channels.
"""

from solutions.rag.application.components.conversation_policy import SupportResponder
from solutions.rag.config import RagSolutionSettings


def test_default_support_channels_are_empty():
    s = RagSolutionSettings()
    assert s.escalation_hotline == "" and s.escalation_support_method == "" and s.escalation_instructions == ""


def test_unconfigured_support_reply_asks_for_no_credentials_or_fake_number():
    support = SupportResponder(hotline="", support_method="", instructions="")
    for text in (support.handoff("T-1"), support.contact_line(), support.feedback("T-2")):
        lowered = text.lower()
        assert "mật khẩu" not in lowered and "1900" not in text and "ultraviewer" not in lowered
    assert "T-1" in support.handoff("T-1")  # the request is still recorded
