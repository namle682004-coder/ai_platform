"""
Common domain services and utilities.
"""

import sys
from common import chunking
from common.chunking import DocumentChunk, PiiSanitizer, TextChunker, TokenChunker

# Backward-compatibility alias for common.services.chunker
sys.modules[__name__ + ".chunker"] = chunking

__all__ = [
    "DocumentChunk",
    "PiiSanitizer",
    "TextChunker",
    "TokenChunker",
    "chunking",
]
