from __future__ import annotations

import json
import os
from urllib import error, request


def configured_embeddings() -> bool:
    return bool(
        os.getenv("AZURE_OPENAI_ENDPOINT")
        and os.getenv("AZURE_OPENAI_API_KEY")
        and os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    )


def embedding_api_version() -> str:
    return os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")


class AzureOpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
    ) -> None:
        self.endpoint = (endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")).rstrip("/")
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY", "")
        self.deployment = deployment or os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.api_key and self.deployment)

    def embed_text(self, text: str) -> list[float]:
        embeddings = self.embed_texts([text])
        return embeddings[0] if embeddings else []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.configured:
            return [[] for _text in texts]

        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}/embeddings"
            f"?api-version={embedding_api_version()}"
        )

        payload = {"input": texts}

        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        req.add_header("api-key", self.api_key)
        req.add_header("Content-Type", "application/json")

        try:
            with request.urlopen(req, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8", errors="ignore"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Azure OpenAI embeddings request failed: {exc.code} {detail}") from exc
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Azure OpenAI embeddings request failed.") from exc

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            return [[] for _text in texts]

        embeddings: list[list[float]] = [[] for _text in texts]
        for position, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            index = item.get("index", position)
            embedding = item.get("embedding")
            if not isinstance(index, int) or not 0 <= index < len(embeddings) or not isinstance(embedding, list):
                continue
            embeddings[index] = [float(value) for value in embedding]
        return embeddings
