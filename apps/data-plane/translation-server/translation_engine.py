"""
Enterprise CTranslate2 High-Performance Neural Machine Translation Engine.
Supports Helsinki-NLP / Opus-MT / NLLB-200 with INT8 / FP16 Quantization.
Compliant with Clean Architecture Data-Plane & SRS Section 2.3 & 6.1.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

import torch
from transformers import AutoTokenizer

# Auto-inject nvidia site-packages library paths for dynamic CTranslate2 CUDA linking
for sp in [p for p in sys.path if "site-packages" in p]:
    cublas_lib = os.path.join(sp, "nvidia", "cublas", "lib")
    cudnn_lib = os.path.join(sp, "nvidia", "cudnn", "lib")
    if os.path.isdir(cublas_lib) and cublas_lib not in os.environ.get("LD_LIBRARY_PATH", ""):
        os.environ["LD_LIBRARY_PATH"] = cublas_lib + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    if os.path.isdir(cudnn_lib) and cudnn_lib not in os.environ.get("LD_LIBRARY_PATH", ""):
        os.environ["LD_LIBRARY_PATH"] = cudnn_lib + ":" + os.environ.get("LD_LIBRARY_PATH", "")

try:
    from .config import translation_settings
except (ImportError, ValueError):
    from config import translation_settings

logger = logging.getLogger("aip-translation.engine")

# Canonical FLORES-200 / ISO Language Codes Map
LANG_CODE_MAP = {
    "vi": "vie_Latn",
    "en": "eng_Latn",
    "zh": "zho_Hans",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "fr": "fra_Latn",
    "de": "deu_Latn",
}


class CTranslate2TranslationEngine:
    def __init__(self):
        self._translator = None
        self._tokenizer = None
        self._initialized = False
        self._backend = "Uninitialized"
        self._device = "cpu"
        self._model_path = ""

    def initialize(self, force_device: Optional[str] = None):
        if self._initialized:
            return

        if force_device:
            self._device = force_device
        elif translation_settings.device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = translation_settings.device

        base_dir = translation_settings.model_registry_path
        candidate_paths = [
            os.path.join(base_dir, "translation", translation_settings.model_name),
            os.path.join(base_dir, translation_settings.model_name),
            os.path.join(
                os.path.dirname(__file__), "models", translation_settings.model_name
            ),
        ]

        resolved_path = None
        for p in candidate_paths:
            if os.path.exists(p):
                resolved_path = p
                break

        self._model_path = resolved_path or candidate_paths[0]

        # 1. Load Tokenizer
        try:
            if resolved_path and os.path.isdir(resolved_path):
                self._tokenizer = AutoTokenizer.from_pretrained(resolved_path)
            else:
                self._tokenizer = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-vi-en")
            logger.info("Translation tokenizer loaded successfully!")
        except Exception as t_err:
            logger.warning(f"Could not load AutoTokenizer: {t_err}")

        # 2. Load CTranslate2 Translator
        try:
            import ctranslate2

            if resolved_path and os.path.isdir(resolved_path):
                if self._device == "cuda":
                    try:
                        logger.info(
                            f"Loading CTranslate2 model from {resolved_path} on GPU (CUDA, {translation_settings.compute_type})..."
                        )
                        translator = ctranslate2.Translator(
                            resolved_path,
                            device="cuda",
                            device_index=translation_settings.device_index,
                            compute_type=translation_settings.compute_type,
                            inter_threads=translation_settings.inter_threads,
                            intra_threads=translation_settings.intra_threads,
                        )
                        # Warmup test to verify CUDA GEMM libraries (libcublas) are available
                        translator.translate_batch([[" Xin", " chào"]])
                        self._translator = translator
                        self._backend = f"CTranslate2 Native C++ Engine (CUDA, {translation_settings.compute_type})"
                        self._device = "cuda"
                        self._initialized = True
                        logger.info("CTranslate2 GPU model successfully loaded & warmed up!")
                        return
                    except Exception as exc:
                        logger.warning(
                            f"CTranslate2 CUDA mode unavailable ({exc}); falling back to CPU mode..."
                        )
                        self._device = "cpu"
                        self._translator = None

                # CPU Mode
                try:
                    logger.info(
                        f"Loading CTranslate2 model from {resolved_path} on CPU (int8)..."
                    )
                    translator = ctranslate2.Translator(
                        resolved_path,
                        device="cpu",
                        device_index=0,
                        compute_type="int8",
                        inter_threads=translation_settings.inter_threads,
                        intra_threads=translation_settings.intra_threads,
                    )
                    self._translator = translator
                    self._backend = "CTranslate2 Native C++ Engine (CPU, int8)"
                    self._device = "cpu"
                    self._initialized = True
                    logger.info(
                        "CTranslate2 CPU model successfully loaded into memory!"
                    )
                    return
                except Exception as exc:
                    logger.warning(f"Could not load CTranslate2 model on CPU: {exc}")
        except ImportError:
            logger.info("ctranslate2 package not found in current environment.")
        except Exception as exc:
            logger.warning(f"Could not load CTranslate2 model from {self._model_path}: {exc}")

        self._backend = "CTranslate2 model unavailable"
        logger.error(self._backend)

    def normalize_lang(self, lang: str) -> str:
        if not lang:
            return "vie_Latn"
        clean = lang.strip().lower()
        return LANG_CODE_MAP.get(clean, lang)

    async def translate_text(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        beam_size: Optional[int] = None,
    ) -> dict:
        self.initialize()
        if self._translator is None:
            if os.getenv("TEST_MODE") == "true":
                translated = f"[Translated] {text}"
                return {
                    "translated_text": translated,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "execution_time_ms": 1.0,
                    "prompt_tokens": len(text.split()),
                    "completion_tokens": len(translated.split()),
                    "total_tokens": len(text.split()) + len(translated.split()),
                    "character_count": len(text),
                    "word_count": len(text.split()),
                    "backend": "test_mock",
                    "device": "cpu",
                    "compute_type": "none",
                    "beam_size": beam_size or 4,
                }
            raise RuntimeError(self._backend)
        start_time = time.time()

        _src = self.normalize_lang(source_lang)
        _tgt = self.normalize_lang(target_lang)

        if self._translator is not None:
            try:
                # 1. Subword tokenization via tokenizer
                if self._tokenizer is not None:
                    tokens = self._tokenizer.tokenize(text)
                    subwords = [tokens]
                else:
                    words = text.strip().split()
                    subwords = [words]

                prompt_tokens = len(subwords[0])

                # 2. Fast C++ Inference
                bs = beam_size or translation_settings.beam_size
                results = self._translator.translate_batch(
                    subwords,
                    beam_size=bs,
                    max_decoding_length=translation_settings.max_decoding_length,
                    repetition_penalty=1.2,
                    no_repeat_ngram_size=3,
                )
                output_tokens = results[0].hypotheses[0]
                completion_tokens = len(output_tokens)

                # 3. Proper Subword Decoding
                if self._tokenizer is not None:
                    try:
                        translated_text = self._tokenizer.decode(
                            self._tokenizer.convert_tokens_to_ids(output_tokens)
                        )
                    except Exception:
                        translated_text = " ".join(output_tokens)
                else:
                    translated_text = " ".join(output_tokens)

                # 4. Clean formatting
                translated_text = (
                    translated_text.replace("<unk>", "").replace("▁", " ").strip()
                )
                translated_text = " ".join(translated_text.split())
                elapsed = (time.time() - start_time) * 1000

                return {
                    "translated_text": translated_text,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "execution_time_ms": round(elapsed, 2),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "character_count": len(text),
                    "word_count": len(text.split()),
                    "backend": self._backend,
                    "device": self._device,
                    "compute_type": translation_settings.compute_type,
                    "beam_size": bs,
                }
            except Exception as exc:
                logger.exception("CTranslate2 execution error")
                raise RuntimeError(f"CTranslate2 translation failed: {exc}") from exc

    def get_status(self) -> dict:
        is_healthy = self._translator is not None or os.getenv("TEST_MODE") == "true"
        return {
            "status": "healthy" if is_healthy else "degraded",
            "service": "translation-server",
            "backend": self._backend if self._translator is not None else ("test_mock" if os.getenv("TEST_MODE") == "true" else self._backend),
            "device": self._device,
            "cuda_available": torch.cuda.is_available(),
            "model_path": self._model_path,
            "compute_type": translation_settings.compute_type,
            "beam_size": translation_settings.beam_size,
        }


translation_engine = CTranslate2TranslationEngine()
