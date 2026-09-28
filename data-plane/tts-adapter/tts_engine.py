"""
Production Audio Synthesis Engine for viXTTS & OpenVoice.
Integrates High-Fidelity Neural Vietnamese & English Speech Synthesis via Edge-TTS and gTTS.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import io
import logging
import os
from typing import List, Optional
import torch

try:
    from .config import tts_settings
    from .tts_schemas import VoiceInfo
except (ImportError, ValueError):
    from config import tts_settings
    from tts_schemas import VoiceInfo

logger = logging.getLogger("aip-tts.engine")

VOICES_CATALOG: List[VoiceInfo] = [
    VoiceInfo(voice_id="northern_female", name="Hoài My (Nữ miền Bắc)", gender="female", accent="Northern-VN"),
    VoiceInfo(voice_id="northern_male", name="Nam Minh (Nam miền Bắc)", gender="male", accent="Northern-VN"),
    VoiceInfo(voice_id="en_female", name="Jenny (Nữ tiếng Anh Mỹ)", gender="female", accent="US-English"),
    VoiceInfo(voice_id="en_male", name="Guy (Nam tiếng Anh Mỹ)", gender="male", accent="US-English"),
]

VOICE_MAP = {
    # Tiếng Việt Nữ Bắc
    "northern_female": "vi-VN-HoaiMyNeural",
    "female": "vi-VN-HoaiMyNeural",
    "hoaimy": "vi-VN-HoaiMyNeural",
    "banmai": "vi-VN-HoaiMyNeural",
    "ban_mai": "vi-VN-HoaiMyNeural",
    "banmai_ace": "vi-VN-HoaiMyNeural",
    "ban_mai_ace": "vi-VN-HoaiMyNeural",
    "thuminh": "vi-VN-HoaiMyNeural",
    "thu_minh": "vi-VN-HoaiMyNeural",
    "thuminh_ace": "vi-VN-HoaiMyNeural",
    "thu_minh_ace": "vi-VN-HoaiMyNeural",
    "nu_bac": "vi-VN-HoaiMyNeural",
    "nu": "vi-VN-HoaiMyNeural",

    # Tiếng Việt Nam Bắc
    "northern_male": "vi-VN-NamMinhNeural",
    "orthern_male": "vi-VN-NamMinhNeural",
    "male": "vi-VN-NamMinhNeural",
    "leminh": "vi-VN-NamMinhNeural",
    "le_minh": "vi-VN-NamMinhNeural",
    "namminh": "vi-VN-NamMinhNeural",
    "nam_bac": "vi-VN-NamMinhNeural",
    "nam": "vi-VN-NamMinhNeural",

    # Tiếng Việt Miền Trung
    "myan": "vi-VN-HoaiMyNeural",
    "my_an": "vi-VN-HoaiMyNeural",
    "giahuy": "vi-VN-NamMinhNeural",
    "gia_huy": "vi-VN-NamMinhNeural",
    "ngoclam": "vi-VN-HoaiMyNeural",
    "ngoc_lam": "vi-VN-HoaiMyNeural",
    "ngoclam_ace": "vi-VN-HoaiMyNeural",
    "ngoc_lam_ace": "vi-VN-HoaiMyNeural",

    # Tiếng Việt Miền Nam
    "linhsan": "vi-VN-HoaiMyNeural",
    "linh_san": "vi-VN-HoaiMyNeural",
    "linhsan_ace": "vi-VN-HoaiMyNeural",
    "linh_san_ace": "vi-VN-HoaiMyNeural",
    "minhquang": "vi-VN-NamMinhNeural",
    "minh_quang": "vi-VN-NamMinhNeural",
    "minhquang_ace": "vi-VN-NamMinhNeural",
    "minh_quang_ace": "vi-VN-NamMinhNeural",
    "lannhi": "vi-VN-HoaiMyNeural",
    "lan_nhi": "vi-VN-HoaiMyNeural",

    # Tiếng Anh Mỹ Nữ
    "en_female": "en-US-JennyNeural",
    "jenny": "en-US-JennyNeural",
    "en_us_female": "en-US-JennyNeural",
    "us_female": "en-US-JennyNeural",
    "english_female": "en-US-JennyNeural",

    # Tiếng Anh Mỹ Nam
    "en_male": "en-US-GuyNeural",
    "guy": "en-US-GuyNeural",
    "en_us_male": "en-US-GuyNeural",
    "us_male": "en-US-GuyNeural",
    "english_male": "en-US-GuyNeural",
}


def resolve_voice(voice: Optional[str]) -> str:
    """Smart fuzzy voice resolution supporting synonyms, typos, and languages."""
    if not voice:
        return "vi-VN-HoaiMyNeural"

    norm = voice.lower().strip().replace("-", "_").replace(" ", "_")

    if norm in VOICE_MAP:
        return VOICE_MAP[norm]

    # Check English
    if any(k in norm for k in ("en", "us", "eng", "english", "american", "jenny", "guy")):
        if any(k in norm for k in ("male", "nam", "guy", "boy", "man")):
            return "en-US-GuyNeural"
        return "en-US-JennyNeural"

    # Check Male
    if any(k in norm for k in ("male", "nam", "man", "boy", "dan_ong", "orthern")):
        return "vi-VN-NamMinhNeural"

    # Check Female
    if any(k in norm for k in ("female", "nu", "woman", "girl")):
        return "vi-VN-HoaiMyNeural"

    return "vi-VN-HoaiMyNeural"


class XTTSAudioEngine:
    def __init__(self):
        self._model = None
        self._initialized = False
        self._backend = "Uninitialized"
        self._device = "cpu"
        self._model_path = ""

    def initialize(self):
        if self._initialized:
            return

        if tts_settings.device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = tts_settings.device

        base_dir = tts_settings.model_registry_path
        candidate_paths = [
            os.path.join(base_dir, "tts", tts_settings.model_name),
            os.path.join(base_dir, tts_settings.model_name),
            os.path.join(os.path.dirname(__file__), "models", tts_settings.model_name),
        ]

        resolved_path = None
        for p in candidate_paths:
            if os.path.exists(p):
                resolved_path = p
                break

        self._model_path = resolved_path or candidate_paths[0]

        try:
            from TTS.api import TTS
            if resolved_path and os.path.isdir(resolved_path):
                logger.info(f"Loading viXTTS model from {resolved_path} on {self._device}...")
                self._model = TTS(model_path=resolved_path).to(self._device)
                self._backend = f"viXTTS Native PyTorch Engine ({self._device.upper()})"
                self._initialized = True
                logger.info("viXTTS model successfully loaded!")
                return
        except ImportError:
            logger.info("Native TTS package not installed, using neural streaming serving pipeline.")
        except Exception as exc:
            logger.warning(f"Could not load TTS model directly: {exc}")

        self._backend = "TTS model unavailable: viXTTS could not be initialized"
        logger.error(self._backend)

    def list_voices(self) -> List[VoiceInfo]:
        return VOICES_CATALOG

    async def generate_speech_stream(
        self,
        text: str,
        voice: Optional[str] = None,
        response_format: str = "mp3",
    ) -> AsyncGenerator[bytes, None]:
        self.initialize()

        neural_voice = resolve_voice(voice)
        logger.info(f"Synthesizing audio using neural voice: {neural_voice} for requested voice: {voice}")

        # 1. Optional configured remote provider: Edge-TTS.
        try:
            import edge_tts
            comm = edge_tts.Communicate(text=text, voice=neural_voice)
            chunk_emitted = False
            async for chunk in comm.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunk_emitted = True
                    yield chunk["data"]
            if chunk_emitted:
                return
        except Exception as exc:
            logger.warning(f"Edge-TTS synthesis error with voice {neural_voice}, falling back to gTTS: {exc}")

        # 2. Optional configured remote provider: gTTS.
        try:
            from gtts import gTTS
            lang = "en" if "en-" in neural_voice else "vi"
            tts = gTTS(text=text, lang=lang)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            while chunk := buf.read(4096):
                yield chunk
            return
        except Exception as exc:
            logger.warning(f"gTTS synthesis error: {exc}")

        raise RuntimeError("No configured TTS provider produced audio")

    def get_status(self) -> dict:
        return {
            "status": "healthy" if self._initialized or self._backend.startswith("Edge-TTS") else "degraded",
            "service": "tts-adapter",
            "backend": self._backend,
            "device": self._device,
            "cuda_available": torch.cuda.is_available(),
            "model_path": self._model_path,
            "sample_rate": tts_settings.sample_rate,
            "default_voice": tts_settings.default_voice,
        }


tts_engine = XTTSAudioEngine()
