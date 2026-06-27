from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from urllib import error, parse, request


DOCUMENT_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")


@dataclass(frozen=True)
class DocumentExtraction:
    content: str
    content_type: str
    extraction_method: str
    page_count: int | None = None
    confidence: float | None = None


def looks_like_document_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = parse.urlparse(url)
    except ValueError:
        return False
    path = parsed.path.lower()
    return any(path.endswith(extension) for extension in DOCUMENT_EXTENSIONS)


def document_content_type(url: str) -> str:
    path = parse.urlparse(url).path.lower()
    if path.endswith(".pdf"):
        return "application/pdf"
    if path.endswith(".png"):
        return "image/png"
    if path.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if path.endswith(".webp"):
        return "image/webp"
    if path.endswith((".tif", ".tiff")):
        return "image/tiff"
    if path.endswith(".bmp"):
        return "image/bmp"
    return "application/octet-stream"


class AzureDocumentIntelligenceClient:
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self.endpoint = (endpoint or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")).rstrip("/")
        self.api_key = api_key or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
        self.api_version = api_version or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_API_VERSION", "2024-11-30")

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.api_key)

    def extract_from_url(self, document_url: str) -> DocumentExtraction | None:
        if not self.configured:
            return None

        analyze_url = (
            f"{self.endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze"
            f"?api-version={self.api_version}&outputContentFormat=markdown"
        )
        payload = json.dumps({"urlSource": document_url}).encode("utf-8")
        operation_url = self._post_analyze(analyze_url, payload)
        if not operation_url:
            return None
        result = self._poll_result(operation_url)
        if not result:
            return None

        analyze_result = result.get("analyzeResult") if isinstance(result, dict) else None
        if not isinstance(analyze_result, dict):
            return None
        content = analyze_result.get("content")
        if not isinstance(content, str) or not content.strip():
            return None

        pages = analyze_result.get("pages")
        page_count = len(pages) if isinstance(pages, list) else None
        confidence = average_document_confidence(analyze_result)
        return DocumentExtraction(
            content=content,
            content_type=document_content_type(document_url),
            extraction_method="azure_document_intelligence",
            page_count=page_count,
            confidence=confidence,
        )

    def _post_analyze(self, url: str, payload: bytes) -> str | None:
        req = request.Request(url, data=payload, method="POST")
        req.add_header("Ocp-Apim-Subscription-Key", self.api_key)
        req.add_header("Content-Type", "application/json")
        try:
            with request.urlopen(req, timeout=20) as response:
                return response.headers.get("Operation-Location")
        except (error.HTTPError, error.URLError, TimeoutError, ValueError):
            return None

    def _poll_result(self, operation_url: str) -> Mapping[str, object] | None:
        for _ in range(8):
            req = request.Request(operation_url)
            req.add_header("Ocp-Apim-Subscription-Key", self.api_key)
            try:
                with request.urlopen(req, timeout=20) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            except (error.HTTPError, error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
                return None

            if isinstance(payload, dict) and payload.get("status") == "succeeded":
                return payload
            if isinstance(payload, dict) and payload.get("status") == "failed":
                return None
            time.sleep(1)
        return None


def average_document_confidence(analyze_result: Mapping[str, object]) -> float | None:
    pages = analyze_result.get("pages")
    if not isinstance(pages, list):
        return None
    confidences: list[float] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        words = page.get("words")
        if not isinstance(words, list):
            continue
        for word in words:
            if isinstance(word, dict) and isinstance(word.get("confidence"), (int, float)):
                confidences.append(float(word["confidence"]))
    if not confidences:
        return None
    return round(sum(confidences) / len(confidences), 3)


def extract_document_from_url(document_url: str) -> DocumentExtraction | None:
    return AzureDocumentIntelligenceClient().extract_from_url(document_url)
