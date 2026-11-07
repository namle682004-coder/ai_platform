"""
GET /v1/rag/tickets/{id}/conversation: the end of the conversation that led to a ticket, for the inbox page.
Conversations belong to end users: administrators of the ticket's tenant only.
"""

import asyncio
import importlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from solutions.rag.application.dtos import ChatMessageDTO, ChatSessionDTO

# The api package exports the router under the same name: take the module itself.
chat_router = importlib.import_module("solutions.rag.interfaces.api.chat_router")


def _request(role="admin", tenant="t1", user="staff_1"):
    headers = [(b"x-user-role", role.encode()), (b"x-tenant-id", tenant.encode()), (b"x-user-id", user.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""})


class Repo:
    def __init__(self, tickets):
        self.tickets, self.appended = tickets, []

    async def get_escalation_ticket(self, ticket_id, tenant_id):
        t = self.tickets.get(ticket_id)
        return dict(t) if t and t["tenant_id"] == tenant_id else None

    async def append_message(self, session_id, user_id, tenant_id, message, title=None):
        self.appended.append((session_id, user_id, tenant_id, dict(message)))
        return True

    async def update_escalation_ticket(self, ticket_id, tenant_id, fields):
        self.tickets[ticket_id].update(fields)
        return dict(self.tickets[ticket_id])

    async def count_open_tickets(self, tenant_id, session_id):
        return sum(1 for t in self.tickets.values()
                   if t["tenant_id"] == tenant_id and t["session_id"] == session_id and t.get("status") != "resolved")


class Sessions:
    def __init__(self, session):
        self.session, self.calls = session, []

    async def get_session(self, session_id, user_id, tenant_id):
        self.calls.append((session_id, user_id, tenant_id))
        return self.session if session_id == self.session.session_id and tenant_id == self.session.tenant_id else None


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "true")
    msgs = [ChatMessageDTO(role=r, content=c, timestamp=ts) for r, c, ts in [
        ("user", "Xin chào", 1000), ("assistant", "Chào bạn", 1001),
        ("user", "Thủ tục gia hạn chữ ký số?", 1100), ("assistant", "Chưa có thông tin trong tài liệu.", 1102),
        ("user", "Câu hỏi sau ticket", 5000), ("assistant", "…", 5001),
    ]]
    session = ChatSessionDTO(session_id="s1", user_id="u1", tenant_id="t1", title="x", messages=msgs,
                             created_at=1000, updated_at=5001)
    tickets = {"tk1": {"ticket_id": "tk1", "tenant_id": "t1", "session_id": "s1", "user_id": "u1",
                       "query": "Thủ tục gia hạn chữ ký số?", "created_at": 1101}}
    sessions = Sessions(session)
    repo = Repo(tickets)
    monkeypatch.setattr(chat_router, "_session_repo", repo)
    monkeypatch.setattr(chat_router, "session_use_case", sessions)
    sessions.repo = repo
    return sessions


def test_admin_sees_the_turns_up_to_the_ticket_and_the_bot_reply(wired):
    out = asyncio.run(chat_router.ticket_conversation("tk1", _request()))
    assert [m["content"] for m in out["messages"]] == [
        "Xin chào", "Chào bạn", "Thủ tục gia hạn chữ ký số?", "Chưa có thông tin trong tài liệu."]
    assert wired.calls == [("s1", "u1", "t1")]  # read as the ticket's own user, in the ticket's tenant


def test_conversations_are_for_administrators_only(wired):
    with pytest.raises(HTTPException) as e:
        asyncio.run(chat_router.ticket_conversation("tk1", _request(role="user")))
    assert e.value.status_code == 403


def test_a_session_of_another_tenant_is_never_shown(wired, monkeypatch):
    other = ChatSessionDTO(session_id="s1", user_id="u1", tenant_id="t2", title="x",
                           messages=[ChatMessageDTO(role="user", content="bí mật của t2", timestamp=1000)],
                           created_at=1000, updated_at=1000)

    class Any_:
        async def get_session(self, session_id, user_id, tenant_id):
            return other  # the session store matches on the id only

    monkeypatch.setattr(chat_router, "session_use_case", Any_())
    assert asyncio.run(chat_router.ticket_conversation("tk1", _request()))["messages"] == []


def test_a_ticket_of_another_tenant_is_not_found(wired):
    with pytest.raises(HTTPException) as e:
        asyncio.run(chat_router.ticket_conversation("tk1", _request(tenant="t2")))
    assert e.value.status_code == 404 and not wired.calls


# ---------------------------------------------------------------- customer service replies to the customer
def test_customer_service_reply_goes_into_the_customers_conversation_and_closes_the_ticket(wired):
    body = chat_router.TicketReplyDTO(message="Chào anh, thủ tục gia hạn: …")
    out = asyncio.run(chat_router.reply_to_ticket("tk1", body, _request(role="support")))
    session_id, user_id, tenant_id, msg = wired.repo.appended[0]
    assert (session_id, user_id, tenant_id) == ("s1", "u1", "t1")  # the customer's own conversation
    assert msg["author"] == "agent" and msg["role"] == "assistant" and msg["content"] == "Chào anh, thủ tục gia hạn: …"
    assert out["ticket"]["status"] == "resolved" and out["ticket"]["reply"] == msg["content"]
    assert out["ticket"]["replied_by"] == "staff_1"


def test_a_reply_can_leave_the_ticket_open(wired):
    body = chat_router.TicketReplyDTO(message="Bên em đang kiểm tra, sẽ báo lại anh trong hôm nay.", resolve=False)
    out = asyncio.run(chat_router.reply_to_ticket("tk1", body, _request(role="agent")))
    assert out["ticket"].get("status") != "resolved" and out["ticket"]["reply"]


def test_only_customer_service_replies(wired):
    with pytest.raises(HTTPException) as e:
        asyncio.run(chat_router.reply_to_ticket("tk1", chat_router.TicketReplyDTO(message="x"), _request(role="user")))
    assert e.value.status_code == 403 and not wired.repo.appended


def test_the_customer_receives_replies_of_their_own_conversation_only(wired):
    wired.session.messages.append(ChatMessageDTO(role="assistant", author="agent", content="Trả lời của CSKH",
                                                 timestamp=6000))
    mine = asyncio.run(chat_router.session_agent_replies("s1", _request(role="user", user="u1"), since=5500))
    assert [r["content"] for r in mine["replies"]] == ["Trả lời của CSKH"] and mine["pending"] == 1
    assert asyncio.run(chat_router.session_agent_replies("s1", _request(role="user", user="u1"), since=6000))["replies"] == []
    with pytest.raises(HTTPException) as e:  # someone else knowing the session id
        asyncio.run(chat_router.session_agent_replies("s1", _request(role="user", user="u2"), since=0))
    assert e.value.status_code == 404


def test_the_bot_never_takes_a_customer_service_reply_as_its_own_answer():
    from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase

    class Store:
        async def get_session(self, session_id, user_id, tenant_id):
            import time
            return {"updated_at": time.time(), "messages": [
                {"role": "user", "content": "Thủ tục gia hạn?"},
                {"role": "assistant", "content": "Chưa có thông tin."},
                {"role": "assistant", "author": "agent", "content": "CSKH: gia hạn tại quầy."},
            ]}

    uc = RagChatUseCase.__new__(RagChatUseCase)
    uc.session_repo = Store()
    history = asyncio.run(uc._resolve_history("s1", "u1", "t1", None))
    assert [m["content"] for m in history] == ["Thủ tục gia hạn?", "Chưa có thông tin."]
