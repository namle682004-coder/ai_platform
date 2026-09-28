"""Convert the configured Hugging Face translation model to CTranslate2 format."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ctranslate2.converters import TransformersConverter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.getenv("TRANSLATION_MODEL_SOURCE", "Helsinki-NLP/opus-mt-vi-en"),
        help="Hugging Face model ID or local snapshot path",
    )
    parser.add_argument(
        "--output",
        default=os.getenv(
            "TRANSLATION_MODEL_OUTPUT", "models/translation/opus-mt-vi-en"
        ),
        help="CTranslate2 model output directory",
    )
    parser.add_argument(
        "--quantization", default=os.getenv("TRANSLATION_QUANTIZATION", "int8")
    )
    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"Converting {args.source} -> {output_dir} ({args.quantization})")
    converter = TransformersConverter(args.source, low_cpu_mem_usage=True)
    converter.convert(str(output_dir), quantization=args.quantization, force=True)
    print(f"CTranslate2 model ready: {output_dir}")


if __name__ == "__main__":
    main()
