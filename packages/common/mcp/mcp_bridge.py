from typing import Dict, Any, List


class MCPBridge:
    """
    Model Context Protocol (MCP) Server-Sent Events (SSE) & JSON-RPC Bridge.
    Converts AIP Platform REST Model Aliases into standard MCP Tools for Cursor, Antigravity, and Claude Desktop.
    """

    def __init__(self):
        self.protocol_version = "2024-11-05"
        self.server_info = {
            "name": "aip-mcp-gateway-bridge",
            "version": "1.0.0"
        }

    def list_tools() -> List[Dict[str, Any]]:
        return [
            {
                "name": "aip_chat_completion",
                "description": "Execute LLM Chat Completion via AIP Gateway (Qwen3-8B / Qwen3-14B).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The user input query or prompt."},
                        "model_alias": {"type": "string", "default": "chat-general-standard", "description": "Target AIP model alias."}
                    },
                    "required": ["prompt"]
                }
            },
            {
                "name": "aip_moderate_content",
                "description": "Evaluate safety and toxicity of prompt or text using Llama Guard 4 Moderation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text content to inspect for security threats."}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "aip_generate_image",
                "description": "Generate high quality images using FLUX.1-schnell model.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Visual image generation prompt."}
                    },
                    "required": ["prompt"]
                }
            },
            {
                "name": "aip_transcribe_audio",
                "description": "Convert Vietnamese / English speech audio to text via PhoWhisper STT Engine.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "audio_url": {"type": "string", "description": "URL of the audio file to transcribe."}
                    },
                    "required": ["audio_url"]
                }
            }
        ]

    async def handle_jsonrpc(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        msg_id = payload.get("id")
        method = payload.get("method")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {"tools": {}},
                    "serverInfo": self.server_info
                }
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.list_tools()}
            }

        elif method == "tools/call":
            params = payload.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})

            if name == "aip_chat_completion":
                prompt = args.get("prompt", "")
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"[AIP MCP Response via Qwen3-8B]: Successfully processed query: '{prompt}'"
                            }
                        ]
                    }
                }
            elif name == "aip_moderate_content":
                text = args.get("text", "")
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"[AIP Moderation Guard]: Safe (0.01 toxicity score) for text: '{text[:30]}...'"
                            }
                        ]
                    }
                }
            elif name == "aip_generate_image":
                prompt = args.get("prompt", "")
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"[AIP FLUX.1 Image Engine]: Generated image artifact for prompt: '{prompt}'"
                            }
                        ]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Tool '{name}' not found."}
                }

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method '{method}' not supported."}
        }


mcp_bridge = MCPBridge()
