from typing import Dict, Any, Optional
from common.models.catalog import AIP_MODEL_CATALOG

# Base JSON Schemas for AI Workload Archetypes
BASE_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "chat": {
        "type": "object",
        "title": "Chat Completion Request",
        "properties": {
            "model": {"type": "string", "description": "Target model alias"},
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                        "content": {"type": "string"},
                    },
                    "required": ["role", "content"],
                },
            },
            "temperature": {"type": "number", "minimum": 0.0, "maximum": 2.0, "default": 0.7},
            "max_tokens": {"type": "integer", "default": 2048},
            "stream": {"type": "boolean", "default": False},
        },
        "required": ["model", "messages"],
    },
    "translation": {
        "type": "object",
        "title": "Translation Request",
        "properties": {
            "text": {"type": "string", "description": "Text to translate"},
            "source_lang": {"type": "string", "default": "en"},
            "target_lang": {"type": "string", "default": "vi"},
        },
        "required": ["text"],
    },
    "stt": {
        "type": "object",
        "title": "Speech to Text Request",
        "properties": {
            "file": {"type": "string", "format": "binary", "description": "Audio file (WAV, MP3, M4A)"},
            "model": {"type": "string", "default": "stt-vn-standard"},
            "language": {"type": "string", "default": "vi"},
        },
        "required": ["file"],
    },
    "tts": {
        "type": "object",
        "title": "Text to Speech Request",
        "properties": {
            "input": {"type": "string", "description": "Text to synthesize"},
            "model": {"type": "string", "default": "tts-vi-standard"},
            "voice": {"type": "string", "default": "northern_female"},
            "speed": {"type": "number", "default": 1.0},
        },
        "required": ["input"],
    },
    "image": {
        "type": "object",
        "title": "Image Generation Request",
        "properties": {
            "prompt": {"type": "string", "description": "Detailed text prompt"},
            "model": {"type": "string", "default": "image-gen-standard"},
            "width": {"type": "integer", "default": 1024},
            "height": {"type": "integer", "default": 1024},
            "num_inference_steps": {"type": "integer", "default": 25},
        },
        "required": ["prompt"],
    },
    "video": {
        "type": "object",
        "title": "Video Generation Request",
        "properties": {
            "prompt": {"type": "string", "description": "Text prompt describing video motion"},
            "model": {"type": "string", "default": "video-gen-standard"},
            "duration_seconds": {"type": "integer", "default": 5},
        },
        "required": ["prompt"],
    },
    "embedding": {
        "type": "object",
        "title": "Vector Embedding Request",
        "properties": {
            "input": {"type": "string", "description": "Text input to encode"},
            "model": {"type": "string", "default": "embed-standard"},
        },
        "required": ["input"],
    },
    "moderation": {
        "type": "object",
        "title": "Content Moderation Request",
        "properties": {
            "input": {"type": "string", "description": "Text or media content to inspect"},
            "model": {"type": "string", "default": "moderation-multimodal"},
        },
        "required": ["input"],
    },
}


class SchemaRegistry:
    """
    Enterprise Dynamic Schema Registry.
    Provides schema definitions for all 21 models defined in the catalog.
    """

    def __init__(self):
        self._custom_schemas: Dict[str, Dict[str, Any]] = {}

    def get_schema_for_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        if model_id in self._custom_schemas:
            return self._custom_schemas[model_id]

        if model_id in AIP_MODEL_CATALOG:
            meta = AIP_MODEL_CATALOG[model_id]
            cat = meta.category
            schema = BASE_SCHEMAS.get(cat, BASE_SCHEMAS["chat"]).copy()
            schema["model_id"] = model_id
            schema["description"] = meta.description
            schema["physical_model"] = meta.physical_model
            return schema

        return None

    def list_schemas(self) -> Dict[str, Any]:
        result = {}
        for alias_id, _meta in AIP_MODEL_CATALOG.items():
            result[alias_id] = self.get_schema_for_model(alias_id)
        return result

    def register_schema(self, model_id: str, schema: Dict[str, Any]):
        self._custom_schemas[model_id] = schema


schema_registry = SchemaRegistry()
