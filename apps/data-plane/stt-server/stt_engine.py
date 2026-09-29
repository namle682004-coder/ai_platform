"""
Production Faster-Whisper Speech-to-Text Engine.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional
import torch

try:
    from .config import stt_settings
    from .stt_schemas import TranscriptionResponse, TranscriptionSegment
except (ImportError, ValueError):
    from config import stt_settings
    from stt_schemas import TranscriptionResponse, TranscriptionSegment

logger = logging.getLogger("aip-stt.engine")


class FasterWhisperEngine:
    def __init__(self):
        self._model = None
        self._initialized = False
        self._backend = "Uninitialized"
        self._device = "cpu"
        self._model_path = ""

    def initialize(self):
        if self._initialized:
            return

        if os.getenv("TEST_MODE") == "true":
            self._backend = "Test Mock Faster-Whisper Engine (CPU)"
            self._initialized = True
            return

        if stt_settings.device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = stt_settings.device

        base_dir = stt_settings.model_registry_path
        candidate_paths = [
            os.path.join(base_dir, "whisper", stt_settings.whisper_model_name),
            os.path.join(base_dir, stt_settings.whisper_model_name),
            os.path.join(os.path.dirname(__file__), "models", stt_settings.whisper_model_name),
        ]

        resolved_path = None
        for p in candidate_paths:
            if os.path.exists(p):
                resolved_path = p
                break

        self._model_path = resolved_path or candidate_paths[0]

        try:
            from faster_whisper import WhisperModel
            model_target = resolved_path if (resolved_path and os.path.isdir(resolved_path)) else "base"
            # Always ensure CPU is safe fallback if libcublas is missing
            try:
                self._model = WhisperModel(
                    model_target,
                    device="cpu",
                    compute_type="int8",
                    num_workers=stt_settings.num_workers,
                )
                self._backend = f"Faster-Whisper ({model_target}) Engine (CPU)"
                self._initialized = True
                logger.info("Faster-Whisper model successfully loaded on CPU!")
                return
            except Exception as cpu_err:
                logger.warning(f"CPU Whisper loading error: {cpu_err}")
        except Exception as exc:
            logger.warning(f"Could not load Faster-Whisper model: {exc}")

        self._backend = "Faster-Whisper model unavailable"
        logger.error(self._backend)

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
        beam_size: Optional[int] = None,
        vad_filter: Optional[bool] = None,
    ) -> TranscriptionResponse:
        self.initialize()
        if os.getenv("TEST_MODE") == "true":
            return TranscriptionResponse(
                text="Xin chào thế giới máy học",
                language=language or "vi",
                duration=2.5,
                segments=[
                    TranscriptionSegment(
                        id=0,
                        start=0.0,
                        end=2.5,
                        text="Xin chào thế giới máy học",
                        avg_logprob=-0.12,
                    )
                ],
            )
        if self._model is None:
            raise RuntimeError(self._backend)
        lang = language or stt_settings.default_language
        use_vad = vad_filter if vad_filter is not None else stt_settings.vad_filter

        if self._model is not None:
            import tempfile
            from pathlib import Path
            suffix = Path(filename).suffix if Path(filename).suffix else ".wav"
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(audio_bytes)
                    tmp_path = tmp.name

                segments_gen, info = self._model.transcribe(
                    tmp_path,
                    language=lang,
                    beam_size=beam_size or stt_settings.beam_size,
                    vad_filter=use_vad,
                    vad_parameters=dict(min_silence_duration_ms=stt_settings.vad_min_silence_duration_ms),
                )
                segments: List[TranscriptionSegment] = []
                full_text_list = []
                for idx, s in enumerate(segments_gen):
                    full_text_list.append(s.text.strip())
                    segments.append(
                        TranscriptionSegment(
                            id=idx,
                            start=round(s.start, 2),
                            end=round(s.end, 2),
                            text=s.text.strip(),
                            avg_logprob=round(s.avg_logprob, 3),
                        )
                    )
                full_text = " ".join(full_text_list)

                return TranscriptionResponse(
                    text=full_text,
                    language=info.language or lang,
                    duration=round(info.duration, 2),
                    segments=segments,
                )
            except Exception as exc:
                logger.exception("Faster-Whisper execution error")
                raise RuntimeError("Faster-Whisper transcription failed") from exc
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

        raise RuntimeError("Faster-Whisper transcription produced no result")

    def get_status(self) -> dict:
        return {
            "status": "healthy" if self._model is not None else "degraded",
            "service": "stt-server",
            "backend": self._backend,
            "device": self._device,
            "cuda_available": torch.cuda.is_available(),
            "model_path": self._model_path,
            "whisper_model": stt_settings.whisper_model_name,
            "vad_filter": stt_settings.vad_filter,
        }


stt_engine = FasterWhisperEngine()
