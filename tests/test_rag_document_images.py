"""
Document images: stored in MinIO at ingestion, referenced by passages through a host-independent path,
shown in answers through signed URLs, served by the media endpoint only for a valid signature.
"""

import asyncio
from typing import Dict

from solutions.rag.application.components import media_assets as m
from solutions.rag.application.components.answer_postprocessor import SanitizeContext, sanitize_answer
from solutions.rag.domain.entities import ParsedDocument, ParsedPage

SECRET = "test-secret"
PREFIX = "/v1/rag/media"
H1, H2 = "0123456789abcdef", "fedcba9876543210"


def test_signed_urls_bind_tenant_document_and_file():
    url = m.signed_url(SECRET, PREFIX, "tenant_a", "doc_1", f"{H1}.png")
    assert url.startswith(f"{PREFIX}/doc_1/{H1}.png?t=tenant_a&s=")
    sig = url.split("s=")[1]
    assert m.verify(SECRET, "tenant_a", "doc_1", f"{H1}.png", sig, 0)
    assert not m.verify(SECRET, "tenant_b", "doc_1", f"{H1}.png", sig, 0)  # another tenant's capability
    assert not m.verify(SECRET, "tenant_a", "doc_2", f"{H1}.png", sig, 0)
    assert not m.verify(SECRET, "tenant_a", "doc_1", f"{H2}.png", sig, 0)
    assert not m.verify("other", "tenant_a", "doc_1", f"{H1}.png", sig, 0)
    # With a lifetime the expiry is signed too and enforced.
    url = m.signed_url(SECRET, PREFIX, "t", "d", f"{H1}.png", ttl_seconds=60, now=1000)
    sig, exp = url.split("s=")[1].split("&e=")
    assert m.verify(SECRET, "t", "d", f"{H1}.png", sig, int(exp), now=1050)
    assert not m.verify(SECRET, "t", "d", f"{H1}.png", sig, int(exp), now=1061)
    assert not m.verify(SECRET, "t", "d", f"{H1}.png", sig, 0, now=1050)  # dropping the expiry breaks it


def test_only_hash_named_images_are_valid_references():
    assert m.valid_ref("doc_7c52f38af4f3", f"{H1}.png")
    assert not m.valid_ref("../etc", f"{H1}.png")
    assert not m.valid_ref("doc", "passwd")
    assert not m.valid_ref("doc", f"{H1}.html")  # never serve markup from the image endpoint


def test_placeholder_urls_of_old_passages_map_to_the_served_path():
    text = f"Bước 1\n![Ảnh](https://storage.enterprise.internal/media/{H1}.png)"
    assert m.rewrite_legacy_urls(text, PREFIX, "doc_1") == f"Bước 1\n![Ảnh]({PREFIX}/doc_1/{H1}.png)"


class FakeStorage:
    def __init__(self, fail=()):
        self.objects: Dict[str, bytes] = {}
        self.fail = set(fail)

    def upload_bytes(self, bucket, object_name, data, content_type="application/octet-stream"):
        if any(object_name.endswith(f) for f in self.fail):
            raise RuntimeError("storage down")
        self.objects[f"{bucket}/{object_name}"] = data
        return f"s3://{bucket}/{object_name}"


def test_ingestion_stores_images_and_rewrites_their_tags():
    from solutions.rag.application.use_cases.ingestion_use_case import DocumentIngestionUseCase

    page = (f"Shipper trả lại tiền.\n![Ảnh minh họa](https://storage.enterprise.internal/media/{H1}.png)\n"
            f"Đoạn khác.\n![Ảnh minh họa](https://storage.enterprise.internal/media/{H2}.jpg)\nHết.")
    doc = ParsedDocument(filename="b.docx", file_type="docx", pages=[ParsedPage(page_number=1, text=page)],
                         metadata={"images": [{"hash": H1, "ext": "png", "data": b"\x89PNG..."},
                                              {"hash": H2, "ext": "jpg", "data": b"\xff\xd8..."}]})
    storage = FakeStorage(fail={f"{H2}.jpg"})
    uc = DocumentIngestionUseCase.__new__(DocumentIngestionUseCase)
    uc.storage = storage
    assert uc._store_images(doc, "tenant_a", "doc_1") == 1
    assert list(storage.objects) == [f"aip-data/media/tenant_a/doc_1/{H1}.png"]
    text = doc.pages[0].text
    assert f"![Ảnh minh họa]({PREFIX}/doc_1/{H1}.png)" in text
    assert H2 not in text and "Hết." in text  # an image that could not be stored leaves no dead link
    assert "data" not in doc.metadata["images"][0]  # bytes are not carried further


def _passage(text, doc="doc_1", tenant="tenant_a"):
    return {"payload": {"doc_id": doc, "tenant_id": tenant, "text": text}}


def test_answer_images_are_signed_while_streaming_and_foreign_ones_dropped():
    passage = _passage(f"Shipper.\n![Ảnh minh họa]({PREFIX}/doc_1/{H1}.png)")
    mapper = m.url_mapper([passage], SECRET, PREFIX)
    ctx = SanitizeContext(allowed_image_urls={f"{PREFIX}/doc_1/{H1}.png"}, image_url_mapper=mapper)
    text, _, _ = sanitize_answer(
        f"Nam shipper trả lại tiền [1].\n\n![Ảnh minh họa]({PREFIX}/doc_1/{H1}.png)\n\n![x](https://evil.example/a.png)", ctx)
    assert f"{PREFIX}/doc_1/{H1}.png?t=tenant_a&s=" in text
    assert "evil.example" not in text


def test_images_of_old_passages_are_signed_for_their_own_document_and_tenant():
    legacy = _passage(f"![Ảnh](https://storage.enterprise.internal/media/{H1}.png)", doc="doc_9", tenant="global")
    url = m.url_mapper([legacy], SECRET, PREFIX, default_tenant="tenant_a")(
        f"https://storage.enterprise.internal/media/{H1}.png")
    assert url.startswith(f"{PREFIX}/doc_9/{H1}.png?t=global&s=")  # the shared document's tenant, not the caller's


def test_cited_passages_bring_their_images_into_the_answer():
    from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase

    uc = RagChatUseCase.__new__(RagChatUseCase)
    p1 = _passage(f"Bài 1.\n![Ảnh minh họa]({PREFIX}/doc_1/{H1}.png)")
    p2 = _passage(f"Bài 2.\n![Biểu đồ]({PREFIX}/doc_1/{H2}.png)")
    cited = [{"index": 1, "doc_id": "doc_1", "text": p1["payload"]["text"]},
             {"index": 2, "doc_id": "doc_1", "text": p2["payload"]["text"]}]
    shown = f"Trả lời [1].\n![Ảnh minh họa]({PREFIX}/doc_1/{H1}.png?t=tenant_a&s=abc)"
    block = uc._attach_images(cited, cited, [p1, p2], "tenant_a", shown)
    assert "**Hình ảnh trong tài liệu:**" in block
    assert H2 in block and H1 not in block  # the image already shown is not repeated
    assert "nguồn [2]" in block
    assert cited[0]["images"][0].startswith(f"{PREFIX}/doc_1/{H1}.png?t=tenant_a&s=")
    assert cited[1]["images"][0].startswith(f"{PREFIX}/doc_1/{H2}.png?t=tenant_a&s=")
    # No images in the passages: nothing is added.
    assert uc._attach_images([{"index": 1, "doc_id": "d", "text": "chữ"}], [], [], "t", "x") == ""


def test_media_endpoint_serves_only_signed_requests(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import importlib

    chat_router = importlib.import_module("solutions.rag.interfaces.api.chat_router")
    stored = {f"media/tenant_a/doc_1/{H1}.png": b"\x89PNGdata"}
    monkeypatch.setattr(chat_router._media_storage, "download_bytes", lambda bucket, key: stored.get(key))
    app = FastAPI()
    app.include_router(chat_router.router)
    client = TestClient(app)
    url = m.signed_url(chat_router.media_secret(), PREFIX, "tenant_a", "doc_1", f"{H1}.png")
    ok = client.get(url)
    assert ok.status_code == 200 and ok.content == b"\x89PNGdata"
    assert ok.headers["content-type"] == "image/png" and ok.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"{PREFIX}/doc_1/{H1}.png").status_code == 403  # unsigned
    assert client.get(url.replace("tenant_a", "tenant_b")).status_code == 403  # signature bound to the tenant
    assert client.get(f"{PREFIX}/doc_1/passwd").status_code == 404
    missing = m.signed_url(chat_router.media_secret(), PREFIX, "tenant_a", "doc_1", f"{H2}.png")
    assert client.get(missing).status_code == 404


def test_document_delete_removes_its_images():
    from solutions.rag.application.use_cases.knowledge_use_case import KnowledgeManagementUseCase

    class Repo:
        async def get_document(self, doc_id):
            return {"doc_id": doc_id, "tenant_id": "tenant_a", "s3_object_name": "documents/x.docx"}

        async def delete_document(self, doc_id, tenant_id):
            return True

    class Vectors:
        async def delete_by_doc_id(self, doc_id, tenant_id):
            return None

    class Storage:
        def __init__(self):
            self.prefixes = []

        def delete_object(self, bucket, name):
            return True

        def delete_prefix(self, bucket, prefix):
            self.prefixes.append(prefix)
            return 2

    storage = Storage()
    uc = KnowledgeManagementUseCase.__new__(KnowledgeManagementUseCase)
    uc.doc_repo, uc.vector_store, uc.storage = Repo(), Vectors(), storage

    async def no_cache(*a, **k):
        return None

    uc._invalidate_tenant_cache = no_cache
    assert asyncio.run(uc.delete_document("doc_1", "tenant_a"))
    assert storage.prefixes == ["media/tenant_a/doc_1/"]


def test_prompt_shows_short_image_aliases_that_resolve_back_in_the_answer():
    from solutions.rag.application.components.prompt_builder import compact_image_tags

    url = f"{PREFIX}/doc_1/{H1}.png"
    assert compact_image_tags(f"Bước 1.\n![Ảnh]({url})") == f"Bước 1.\n![Ảnh](img:{H1[:8]})"
    passage = _passage(f"Bước 1.\n![Ảnh]({url})")
    ctx = SanitizeContext(allowed_image_urls={url}, image_url_mapper=m.url_mapper([passage], SECRET, PREFIX))
    text, _, _ = sanitize_answer(f"Bước 1: mở ứng dụng [1].\n![Ảnh](img:{H1[:8]})\n![Ảnh](img:deadbeef)", ctx)
    assert f"{url}?t=tenant_a&s=" in text and "deadbeef" not in text


def test_prompt_is_sized_with_the_runtime_tokenizer_when_available():
    import asyncio as _asyncio

    from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
    from solutions.rag.application.dtos import RagChatRequestDTO

    class TokenLLM:
        def __init__(self):
            self.counted = 0

        async def context_window(self, model):
            return 1000

        async def count_tokens(self, text, model):
            self.counted += 1
            return len(text)  # one token per character: far denser than the 2.3 chars/token estimate

    class Plan:
        generation_history, user_content = [], "Câu hỏi"
        wrapped = raw_citations = context_chunks = []
        system_prompt, max_tokens = "", None

    chunks = [{"payload": {"doc_id": "d", "chunk_index": i, "text": "x" * 300, "title": "T"}, "score": 1.0 - i / 10}
              for i in range(4)]
    from solutions.rag.application.components.context_selector import candidate_key

    uc = RagChatUseCase.__new__(RagChatUseCase)
    uc.llm_service = TokenLLM()
    plan = Plan()
    _asyncio.run(uc._build_prompt_within_window(plan, RagChatRequestDTO(query="Câu hỏi", max_tokens=200), "q", chunks,
                                                {candidate_key(c): c["score"] for c in chunks}))
    assert uc.llm_service.counted >= 1
    assert len(plan.context_chunks) < 4  # the exact count forced passages out, the estimate would not have


def test_a_full_kv_cache_is_waited_out_not_reported_as_an_outage(monkeypatch):
    from solutions.rag.infrastructure.adapters import model_registry as mr

    class Res:
        def __init__(self, code, body):
            self.status_code, self.text, self.headers = code, body, {}

        def json(self):
            return {"ok": True}

    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, url, json, headers, timeout):
            self.calls += 1
            if self.calls == 1:
                return Res(500, '{"error":{"code":500,"message":"Context size has been exceeded."}}')
            return Res(200, "")

    async def no_sleep(_):
        return None

    monkeypatch.setattr(mr.asyncio, "sleep", no_sleep)
    client = Client()
    assert asyncio.run(mr.post_json_with_retry(client, "http://x/v1/chat/completions", {}, {}, 5.0, max_retries=2)) == {"ok": True}
    assert client.calls == 2


def test_a_cited_passage_brings_the_images_of_its_section():
    from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase

    uc = RagChatUseCase.__new__(RagChatUseCase)
    table = {"payload": {"doc_id": "doc_1", "tenant_id": "tenant_a", "heading": "Shipper trả lại tiền", "chunk_index": 8,
                         "text": "| Nguồn | Lượt xem |\n| --- | --- |\n| Tin tức 24h | 55 |"}}
    photo = {"payload": {"doc_id": "doc_1", "tenant_id": "tenant_a", "heading": "Shipper trả lại tiền", "chunk_index": 9,
                         "text": f"Ngày 2/11 …\n![Ảnh minh họa]({PREFIX}/doc_1/{H1}.png)"}}
    other = {"payload": {"doc_id": "doc_1", "tenant_id": "tenant_a", "heading": "Tour ngắm voi", "chunk_index": 7,
                         "text": f"![Ảnh]({PREFIX}/doc_1/{H2}.png)"}}
    cited = [{"index": 1, "doc_id": "doc_1", "heading": "Shipper trả lại tiền", "text": table["payload"]["text"]}]
    block = uc._attach_images(cited, cited, [table], "tenant_a", "Nam shipper trả lại tiền [1].", [table, photo, other])
    assert H1 in block and H2 not in block  # the photo of the same item, not of another section
    assert len(cited[0]["images"]) == 1 and H1 in cited[0]["images"][0]
