"""
A numbered part named by the question ("Điều 7") that exists in several sub-documents is asked back with the
options, unless the question says which sub-document or which subject it means.
"""

from solutions.rag.application.components.reference_ambiguity import ambiguous_reference, clarification_text


def _c(path, doc="d"):
    return {"payload": {"doc_id": doc, "heading_path": path, "text": "..."}}


BUNDLE = [
    _c("QUY CHẾ – về đánh giá > Chương II – KHUNG > Điều 7. Mức xếp loại đơn vị"),
    _c("QUY ĐỊNH – về tiêu chí > Chương II – TIÊU CHÍ > Điều 7. Công thức tính điểm"),
    _c("QUY CHẾ – về đánh giá > Chương III – VIÊN CHỨC > Điều 12. Mức xếp loại viên chức"),
]


def test_label_in_two_sub_documents_is_asked_back_with_both_options():
    opts = ambiguous_reference("Điều 7 quy định gì?", BUNDLE)  # "quy định" is the verb here, not the sub-document
    assert opts and {o.root.split(" – ")[0] for o in opts} == {"QUY CHẾ", "QUY ĐỊNH"}
    text = clarification_text(opts)
    assert "Mức xếp loại đơn vị" in text and "Công thức tính điểm" in text


def test_question_naming_the_sub_document_or_the_subject_is_not_ambiguous():
    assert ambiguous_reference("Điều 7 của quy chế nói gì?", BUNDLE) is None
    assert ambiguous_reference("Điều 7 về công thức tính điểm?", BUNDLE) is None


def test_label_in_one_sub_document_only_or_not_named_is_not_ambiguous():
    assert ambiguous_reference("Điều 12 quy định gì?", BUNDLE) is None
    assert ambiguous_reference("Mức xếp loại viên chức thế nào?", BUNDLE) is None
    # Headings without a numbered label (sections named by title only) never trigger it.
    assert ambiguous_reference("Lớp 10 học gì?", [_c("KHUNG > LỚP 10 > Chủ đề A"), _c("KHUNG > LỚP 11 > Chủ đề A")]) is None


def test_same_label_in_two_documents_is_ambiguous():
    docs = [_c("Nghị định A > Điều 5. Phạm vi", "a"), _c("Thông tư B > Điều 5. Đối tượng", "b")]
    assert ambiguous_reference("Điều 5 là gì?", docs)
