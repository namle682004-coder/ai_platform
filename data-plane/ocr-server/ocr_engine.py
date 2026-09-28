"""
Production OCR & Document Processing Engine.
"""

from __future__ import annotations

import io
import logging
import os
import time
from typing import List
import torch

try:
    from .config import ocr_settings
    from .ocr_schemas import BoundingBox, OCRResponse
except (ImportError, ValueError):
    from config import ocr_settings
    from ocr_schemas import BoundingBox, OCRResponse

logger = logging.getLogger("aip-ocr.engine")


class PaddleOCREngine:
    def __init__(self):
        self._ocr = None
        self._initialized = False
        self._backend = "Uninitialized"
        self._device = "cpu"
        self._model_path = ""

    def initialize(self):
        if self._initialized:
            return

        if os.getenv("TEST_MODE") == "true":
            self._backend = "Test Mock OCR Engine (CPU)"
            self._initialized = True
            return

        if ocr_settings.device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = ocr_settings.device

        base_dir = ocr_settings.model_registry_path
        candidate_paths = [
            os.path.join(base_dir, "ocr", ocr_settings.det_model_name),
            os.path.join(base_dir, "ocr"),
            os.path.join(os.path.dirname(__file__), "models"),
        ]

        resolved_path = None
        for p in candidate_paths:
            if os.path.exists(p):
                resolved_path = p
                break

        self._model_path = resolved_path or candidate_paths[0]

        try:
            from paddleocr import PaddleOCR
            use_gpu = (self._device == "cuda")
            self._ocr = PaddleOCR(use_angle_cls=True, lang=ocr_settings.paddle_lang, use_gpu=use_gpu)
            self._backend = f"PaddleOCR C++ Engine ({self._device.upper()})"
            self._initialized = True
            logger.info("PaddleOCR engine successfully initialized!")
            return
        except ImportError:
            logger.info("paddleocr package not installed, attempting EasyOCR fallback.")
        except Exception as exc:
            logger.warning(f"Could not load PaddleOCR engine: {exc}")

        try:
            import easyocr
            use_gpu = torch.cuda.is_available() and (self._device == "cuda")
            self._easyocr = easyocr.Reader(["vi", "en"], gpu=use_gpu)
            self._backend = f"EasyOCR Multi-Lingual Engine ({'CUDA' if use_gpu else 'CPU'})"
            self._initialized = True
            logger.info(f"EasyOCR engine successfully initialized on {'CUDA' if use_gpu else 'CPU'}!")
            return
        except Exception as easy_err:
            logger.warning(f"Could not load EasyOCR: {easy_err}")

        self._backend = "OCR model unavailable: PaddleOCR and EasyOCR failed to initialize"
        logger.error(self._backend)

    async def process_document(self, file_bytes: bytes, filename: str) -> OCRResponse:
        self.initialize()
        if os.getenv("TEST_MODE") == "true":
            return OCRResponse(
                filename=filename,
                detected_text="CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐỘC LẬP - TỰ DO - HẠNH PHÚC",
                boxes=[
                    BoundingBox(
                        box=[[10, 10], [200, 10], [200, 40], [10, 40]],
                        text="CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
                        confidence=0.985,
                    )
                ],
                execution_time_ms=1.5,
            )
        if self._ocr is None and getattr(self, "_easyocr", None) is None:
            raise RuntimeError(self._backend)
        start_time = time.time()
        boxes: List[BoundingBox] = []
        lines: List[str] = []
        img_cv = None

        # 0. Scan for QR code (common on Vietnamese CCCD and verification documents)
        qr_code_text = ""
        try:
            import cv2
            import numpy as np
            nparr = np.frombuffer(file_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_cv is not None:
                detector = cv2.QRCodeDetector()
                val, _, _ = detector.detectAndDecode(img_cv)
                if val:
                    qr_code_text = val.strip()
                    logger.info(f"Detected QR code on document: {qr_code_text}")
        except Exception as cv_err:
            logger.debug(f"QR detection error: {cv_err}")

        # 1. Primary: PaddleOCR
        if self._ocr is not None:
            try:
                import numpy as np
                from PIL import Image
                img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
                img_np = np.array(img)
                results = self._ocr.ocr(img_np, cls=True)

                boxes = []
                lines = []
                if results and results[0]:
                    for item in results[0]:
                        box_coords = item[0]
                        txt, score = item[1]
                        lines.append(txt)
                        boxes.append(BoundingBox(box=box_coords, text=txt, confidence=round(float(score), 4)))

                if qr_code_text:
                    lines.insert(0, f"QR_CODE: {qr_code_text}")

                elapsed = round((time.time() - start_time) * 1000, 2)
                return OCRResponse(
                    filename=filename,
                    detected_text="\n".join(lines),
                    boxes=boxes,
                    execution_time_ms=elapsed,
                )
            except Exception as exc:
                logger.warning(f"PaddleOCR execution error: {exc}")

        # 2. Secondary: EasyOCR
        if getattr(self, "_easyocr", None) is not None:
            try:
                import cv2
                import numpy as np
                nparr = np.frombuffer(file_bytes, np.uint8)
                img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img_cv is None:
                    from PIL import Image
                    pil_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
                    img_cv = np.array(pil_img)

                results = self._easyocr.readtext(img_cv)
                boxes = []
                lines = []
                for item in results:
                    box_coords = [[float(p[0]), float(p[1])] for p in item[0]]
                    txt = str(item[1]).strip()
                    score = round(float(item[2]), 4)
                    if txt:
                        lines.append(txt)
                        boxes.append(BoundingBox(box=box_coords, text=txt, confidence=score))

                if qr_code_text:
                    lines.insert(0, f"QR_CODE: {qr_code_text}")

                elapsed = round((time.time() - start_time) * 1000, 2)
                return OCRResponse(
                    filename=filename,
                    detected_text="\n".join(lines),
                    boxes=boxes,
                    execution_time_ms=elapsed,
                )
            except Exception as exc:
                logger.warning(f"EasyOCR execution error: {exc}")

        elapsed = round((time.time() - start_time) * 1000, 2)
        if not boxes and not qr_code_text:
            raise RuntimeError("OCR engine produced no detected text")

        detected_text = "\n".join(b.text for b in boxes) if boxes else f"QR_CODE: {qr_code_text}"

        return OCRResponse(
            filename=filename,
            detected_text=detected_text,
            boxes=boxes,
            execution_time_ms=elapsed,
        )

    def get_status(self) -> dict:
        return {
            "status": "healthy" if self._ocr is not None or getattr(self, "_easyocr", None) is not None else "degraded",
            "service": "ocr-server",
            "backend": self._backend,
            "device": self._device,
            "cuda_available": torch.cuda.is_available(),
            "model_path": self._model_path,
        }


ocr_engine = PaddleOCREngine()
