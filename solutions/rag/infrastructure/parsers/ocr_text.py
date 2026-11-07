"""
Post-processing of OCR text from scanned pages.

- `clean_ocr_text`: page borders and specks read as '|', '_' or single marks are removed; a remaining '|'
  is escaped so OCR text never forms a Markdown table.
- `harmonize_diacritics`: Vietnamese OCR confuses tone/vowel marks on some glyphs ("xêp loại", "chât lượng",
  "tôi đa"). A document repeats its phrases, and the same two words without diacritics are almost always the
  same phrase: when one spelling of a word pair dominates the document and another spelling of the same pair
  is rare, the rare one is a misreading and takes the dominant spelling. The evidence is the document itself;
  there is no dictionary or word list.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from typing import Dict, List, Sequence, Tuple

_OCR_NOISE_LINE = re.compile(r"^[\W_]{0,3}$")
_OCR_EDGE_MARKS = re.compile(r"^[|_\s]+|[|_\s]+$")
_WORD = re.compile(r"\w+", re.UNICODE)

# The dominant spelling of a word pair must occur at least this often, and this many times more than the
# spelling it replaces.
MIN_DOMINANT = 4
MIN_RATIO = 4.0


def clean_ocr_text(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        line = _OCR_EDGE_MARKS.sub("", line)
        if _OCR_NOISE_LINE.match(line):
            continue
        lines.append(line.replace("|", "\\|"))
    return "\n".join(lines).strip()


def _base(word: str) -> str:
    w = word.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c) != "Mn")


def _with_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _pairs(text: str) -> List[Tuple[int, re.Match, re.Match]]:
    """Adjacent words separated only by spaces (not across punctuation or line ends)."""
    words = list(_WORD.finditer(text))
    out = []
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        if text[a.end():b.start()].strip(" ") == "" and "\n" not in text[a.end():b.start()]:
            out.append((i, a, b))
    return out


def harmonize_diacritics(texts: Sequence[str]) -> List[str]:
    """Rare spellings of a word pair replaced by the pair's dominant spelling across the given texts."""
    texts = [unicodedata.normalize("NFC", t or "") for t in texts]
    counts: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    for t in texts:
        for _, a, b in _pairs(t):
            counts[(_base(a.group()), _base(b.group()))][(a.group().lower(), b.group().lower())] += 1
    dominant = {k: c.most_common(1)[0] for k, c in counts.items() if len(c) > 1}

    out = []
    for t in texts:
        words = list(_WORD.finditer(t))
        fix: Dict[int, str] = {}
        for i, a, b in _pairs(t):
            key = (_base(a.group()), _base(b.group()))
            if key not in dominant:
                continue
            (dom_a, dom_b), n_dom = dominant[key]
            n_var = counts[key][(a.group().lower(), b.group().lower())]
            if n_dom < MIN_DOMINANT or n_dom < MIN_RATIO * n_var:
                continue
            for j, word, target in ((i, a.group(), dom_a), (i + 1, b.group(), dom_b)):
                if word.lower() != target:
                    fix.setdefault(j, _with_case(word, target))
        if not fix:
            out.append(t)
            continue
        parts, pos = [], 0
        for j, m in enumerate(words):
            if j in fix:
                parts.append(t[pos:m.start()])
                parts.append(fix[j])
                pos = m.end()
        parts.append(t[pos:])
        out.append("".join(parts))
    return out
