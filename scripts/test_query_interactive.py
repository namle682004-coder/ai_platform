#!/usr/bin/env python3
"""
Interactive CLI for testing Vietnamese Query Normalization, Diacritics Restoration,
Acronym Expansion, and Document-level Glossary Harvesting.

Usage:
  # Quick single query:
  python scripts/test_query_interactive.py "ko nop hs bhxh vs hddt thi sao"

  # Interactive prompt mode:
  python scripts/test_query_interactive.py

  # With custom document glossary:
  python scripts/test_query_interactive.py --doc sample_doc.txt "thoi han ky bbbg cua bqltn ntn"
"""

import argparse
import os
import sys
import time

# Ensure project root in PYTHONPATH
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from solutions.rag.application.components.acronym_harvester import acronym_harvester
from solutions.rag.application.components.query_rewriter import RagQueryRewriter


def analyze_query(query: str, custom_glossary=None):
    print("=" * 70)
    print(f"📥 Query gốc:        {query}")

    t0 = time.perf_counter()

    # Step 1: Chat Shorthand Normalization
    shorthand_norm = RagQueryRewriter.normalize_chat_shorthand(query)

    # Step 2: Diacritics Restoration & Casing
    restored = RagQueryRewriter.restore_vietnamese_diacritics(query)

    # Step 3: Acronym Expansion (Global + Custom Doc Glossary)
    expanded = RagQueryRewriter.expand_acronyms(restored, custom_glossary=custom_glossary)

    # Step 4: Dual-token Sparse Representation (BM25)
    sparse_q = RagQueryRewriter.build_dual_token_sparse_query(restored)

    t1 = time.perf_counter()
    latency_ms = (t1 - t0) * 1000

    print(f"💬 Chat Shorthand:   {shorthand_norm}")
    print(f"✨ Khôi phục dấu:    {restored}")
    print(f"🔍 Mở rộng viết tắt: {expanded}")
    print(f"📊 Dual-Token BM25:  {sparse_q}")
    print(f"⚡ Thời gian xử lý:  {latency_ms:.3f} ms")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Test Vietnamese Query & Acronym Processing Engine")
    parser.add_argument("query", nargs="?", default=None, help="Query string to test")
    parser.add_argument("--doc", type=str, default=None, help="Path to document to harvest custom glossary")
    args = parser.parse_args()

    custom_glossary = None
    if args.doc and os.path.exists(args.doc):
        with open(args.doc, "r", encoding="utf-8") as f:
            content = f.read()
        res = acronym_harvester.harvest(content)
        custom_glossary = res.glossary
        print(f"📄 Đã bóc tách {len(custom_glossary)} từ viết tắt từ file: {args.doc}")
        for k, v in custom_glossary.items():
            print(f"   • {k}: {v}")

    if args.query:
        analyze_query(args.query, custom_glossary=custom_glossary)
    else:
        print("\n🚀 CHẾ ĐỘ TEST TƯƠNG TÁC (Gõ 'exit' hoặc 'q' để thoát)\n")
        # Run a quick warm-up
        RagQueryRewriter.restore_vietnamese_diacritics("warmup")

        sample_queries = [
            "ko nop hs bhxh vs hddt thi sao",
            "huong dan lam thu tuc cap gpkd tai co quan nha nuoc",
            "che do thai san cua nld ap dung ntn",
            "tra cuu bctc va quyet toan thue tndn",
            "thoi gian lam viec theo quy dinh ot",
        ]
        print("💡 Một số câu mẫu bạn có thể thử:")
        for sq in sample_queries:
            print(f"   - {sq}")
        print()

        while True:
            try:
                user_input = input("\n👉 Nhập câu truy vấn: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    print("Tạm biệt!")
                    break
                analyze_query(user_input, custom_glossary=custom_glossary)
            except (KeyboardInterrupt, EOFError):
                print("\nThoát.")
                break


if __name__ == "__main__":
    main()
