from typing import Any

import httpx


class ChatCompletions:
    def __init__(self, client: "AIPClient"):
        self._client = client

    def create(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        return self._client._post("/v1/chat/completions", json=payload)


class Embeddings:
    def __init__(self, client: "AIPClient"):
        self._client = client

    def create(
        self,
        model: str,
        input: Any,
    ) -> dict[str, Any]:
        payload = {"model": model, "input": input}
        return self._client._post("/v1/embeddings", json=payload)


class Jobs:
    def __init__(self, client: "AIPClient"):
        self._client = client

    def create(self, job_type: str, alias_name: str, parameters: dict | None = None) -> dict[str, Any]:
        payload = {"job_type": job_type, "alias_name": alias_name, "parameters": parameters or {}}
        return self._client._post("/v1/jobs", json=payload)

    def get_status(self, job_id: str) -> dict[str, Any]:
        return self._client._get(f"/v1/jobs/{job_id}")

    def get_result(self, job_id: str) -> dict[str, Any]:
        return self._client._get(f"/v1/jobs/{job_id}/result")


class AIPClient:
    """
    AI Inference Platform (AIP) Official Enterprise Python SDK Client.
    Provides intuitive methods matching OpenAI & Enterprise SDK standards.
    """

    def __init__(self, api_key: str, base_url: str = "http://localhost:8000"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AIP-Python-SDK/1.0.0",
        }
        self.chat = ChatCompletions(self)
        self.embeddings = Embeddings(self)
        self.jobs = Jobs(self)

    def _post(self, path: str, json: dict) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=60.0) as client:
            res = client.post(url, headers=self.headers, json=json)
            res.raise_for_status()
            return res.json()

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=30.0) as client:
            res = client.get(url, headers=self.headers)
            res.raise_for_status()
            return res.json()
