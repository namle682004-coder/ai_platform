"""
A question naming a numbered part of a document ("Điều 7", "Chương II", "Mẫu số 01", "Annex B") is ambiguous
when that label exists in several sub-documents of the retrieved documents (a bundle holding a regulation and
its implementing rules, each numbering its articles from 1). Answering one of them as if it were the only one
is a wrong answer half of the time; the user is asked which one is meant, with the options listed.

Labels are read from the documents' own heading paths (the part of a heading before its title: "Điều 7" of
"Điều 7. Mức xếp loại …"), never from a list of words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .context_selector import payload_of
from .lexical_evidence import normalize_for_match

# "<word(s)> <number or roman numeral or letter>" at the start of a heading, before its title.
_LABEL = re.compile(r"^\s*((?:[^\W\d_]+\s+){1,2}(?:\d{1,3}|[IVXLCDM]{1,6}|[A-Z]))\b(?=\s*(?:[.:–\-]|$))")
MAX_OPTIONS = 6
# Function words that introduce the document a part belongs to (language, not document vocabulary).
REFERRING_PREPOSITIONS = ("của", "trong", "theo", "tại", "thuộc", "of", "in")


@dataclass
class ReferenceOption:
    label: str  # "Điều 7"
    root: str  # the sub-document ("QUY CHẾ – …")
    heading: str  # the full heading of the part ("Điều 7. Mức xếp loại …")
    path: str


def _label(segment: str) -> str:
    m = _LABEL.match(segment or "")
    return m.group(1).strip() if m else ""


def _contains_phrase(text: str, phrase: str) -> bool:
    t, p = f" {normalize_for_match(text)} ", f" {normalize_for_match(phrase)} "
    return bool(p.strip()) and p in t


def ambiguous_reference(query: str, candidates: Sequence[Any]) -> Optional[List[ReferenceOption]]:
    """The parts of different sub-documents carrying the label the query names; None when not ambiguous."""
    by_label: Dict[str, Dict[str, ReferenceOption]] = {}
    for c in candidates:
        p = payload_of(c)
        segments = [s.strip() for s in str(p.get("heading_path") or "").split(" > ") if s.strip()]
        if len(segments) < 2:
            continue
        root = segments[0]
        for seg in segments[1:]:
            label = _label(seg)
            if label and _contains_phrase(query, label):
                options = by_label.setdefault(normalize_for_match(label), {})
                key = f"{p.get('doc_id')}|{root}"
                options.setdefault(key, ReferenceOption(label=label, root=root, heading=seg,
                                                        path=" > ".join(segments[: segments.index(seg) + 1])))
    for options in by_label.values():
        opts = list(options.values())
        if len({o.root for o in opts}) < 2:
            continue
        # The question already says which sub-document it is about ("Điều 7 của quy chế"): not ambiguous.
        # The name must follow a referring preposition: a sub-document named like a word of the question
        # ("QUY ĐỊNH" in "Điều 7 quy định gì?", where it is the verb) is not a reference to it.
        named = [o for o in opts
                 if any(_contains_phrase(query, f"{prep} {_root_name(o.root)}") for prep in REFERRING_PREPOSITIONS)]
        if len(named) == 1:
            return None
        # Nor when it names the subject of one of the parts ("Điều 7 về công thức tính điểm").
        label_words = set(normalize_for_match(opts[0].label).split())
        words = {w for w in normalize_for_match(query).split() if len(w) > 2 and w not in label_words}
        scores = sorted((len(words & set(normalize_for_match(o.heading).split())) for o in opts), reverse=True)
        if scores[0] > 0 and (len(scores) == 1 or scores[0] > scores[1]):
            return None
        return opts[:MAX_OPTIONS]
    return None


def _root_name(root: str) -> str:
    """The sub-document's name without its description ("QUY CHẾ" of "QUY CHẾ – đánh giá, xếp loại …")."""
    return re.split(r"\s+[–\-:]\s+", root, maxsplit=1)[0]


def clarification_text(options: Sequence[ReferenceOption]) -> str:
    label = options[0].label
    lines = [f"Tài liệu có {len(options)} mục «{label}» thuộc các văn bản khác nhau:"]
    for i, o in enumerate(options, 1):
        lines.append(f"{i}. {o.root} › {o.heading}")
    lines.append(f"\nBạn muốn hỏi «{label}» của văn bản nào? Có thể trả lời bằng số thứ tự hoặc tên văn bản.")
    return "\n".join(lines)
