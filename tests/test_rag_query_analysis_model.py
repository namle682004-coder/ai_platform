"""
Unit test for dedicated query analysis model routing in RagChatUseCase.

Verifies that:
1. When `request.analyzer_model` is passed, analyzer & decomposer use that model directly (dynamic switch).
2. When `rag_settings.query_analysis_model` is configured, analyzer uses that default.
3. When neither is provided, analyzer falls back to `request.model`.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from solutions.rag.application.dtos import RagChatRequestDTO
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
from solutions.rag.config import rag_settings


def _create_mock_analysis():
    mock_analysis = MagicMock()
    mock_analysis.source = "llm"
    mock_analysis.intent = MagicMock(value="DOCUMENT_QUESTION")
    mock_analysis.message_kind = "QUESTION"
    mock_analysis.standalone_query = "cau hoi da viet lai"
    mock_analysis.is_document_question = True
    mock_analysis.new_topic = True
    mock_analysis.focus_terms = set()
    mock_analysis.scope_terms = set()
    for attr in ("challenge", "about_document", "wants_list", "wants_brief", "wants_location",
                 "compare", "answer_format", "aggregate", "count_unit"):
        setattr(mock_analysis, attr, False)
    return mock_analysis


def test_query_analyzer_uses_request_analyzer_model_directly():
    """Client can pass analyzer_model directly in request DTO to switch models per-request."""
    async def _run():
        mock_analyzer = MagicMock()
        mock_analyzer.enabled = True
        mock_analyzer.analyze = AsyncMock(return_value=_create_mock_analysis())

        use_case = RagChatUseCase(
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            llm_service=MagicMock(),
            session_repo=MagicMock(),
            query_analyzer=mock_analyzer,
        )

        request = RagChatRequestDTO(
            query="hỏi gì đó",
            model="claude-3-5-sonnet",      # Generator: Cloud
            analyzer_model="chat-fast",      # Analyzer: Fast Cloud/Local
        )

        with patch.object(use_case, "_plan_document_turn", AsyncMock()):
            await use_case._plan_turn(request, "test_tenant", "user1", "user", "session1", [], None)

        assert mock_analyzer.analyze.await_count == 1
        call_args = mock_analyzer.analyze.await_args
        # Signature: analyze(raw_query, history, llm_service, model, authorization=...)
        assert call_args[0][3] == "chat-fast"

    asyncio.run(_run())


def test_query_analyzer_uses_env_default_when_request_omits_it():
    """When request does not specify analyzer_model, env setting RAG_QUERY_ANALYSIS_MODEL is used."""
    async def _run():
        mock_analyzer = MagicMock()
        mock_analyzer.enabled = True
        mock_analyzer.analyze = AsyncMock(return_value=_create_mock_analysis())

        use_case = RagChatUseCase(
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            llm_service=MagicMock(),
            session_repo=MagicMock(),
            query_analyzer=mock_analyzer,
        )

        request = RagChatRequestDTO(
            query="hỏi gì đó",
            model="claude-3-5-sonnet",
            # analyzer_model is None
        )

        with patch.object(rag_settings, "query_analysis_model", "chat-general-standard"):
            with patch.object(use_case, "_plan_document_turn", AsyncMock()):
                await use_case._plan_turn(request, "test_tenant", "user1", "user", "session1", [], None)

        assert mock_analyzer.analyze.await_count == 1
        call_args = mock_analyzer.analyze.await_args
        assert call_args[0][3] == "chat-general-standard"

    asyncio.run(_run())


def test_query_analyzer_falls_back_to_generator_model():
    """When neither request nor env sets analyzer_model, it falls back to request.model."""
    async def _run():
        mock_analyzer = MagicMock()
        mock_analyzer.enabled = True
        mock_analyzer.analyze = AsyncMock(return_value=_create_mock_analysis())

        use_case = RagChatUseCase(
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            llm_service=MagicMock(),
            session_repo=MagicMock(),
            query_analyzer=mock_analyzer,
        )

        request = RagChatRequestDTO(
            query="hỏi gì đó",
            model="chat-general-standard",
        )

        with patch.object(rag_settings, "query_analysis_model", None):
            with patch.object(use_case, "_plan_document_turn", AsyncMock()):
                await use_case._plan_turn(request, "test_tenant", "user1", "user", "session1", [], None)

        assert mock_analyzer.analyze.await_count == 1
        call_args = mock_analyzer.analyze.await_args
        assert call_args[0][3] == "chat-general-standard"

    asyncio.run(_run())
