from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
from collections.abc import Mapping
from dataclasses import dataclass
from urllib import error, parse, request


DOCUMENT_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024


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
        result = self._poll_result(operation_url) if operation_url else None
        if not result:
            downloaded = self._download_document(document_url)
            if not downloaded:
                return None
            content, content_type = downloaded
            return self.extract_from_bytes(content, content_type=content_type)
        return self._document_extraction(result, content_type=document_content_type(document_url))

    def extract_from_bytes(self, content: bytes, *, content_type: str) -> DocumentExtraction | None:
        if not self.configured or not content:
            return None
        analyze_url = (
            f"{self.endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze"
            f"?api-version={self.api_version}&outputContentFormat=markdown"
        )
        operation_url = self._post_analyze(analyze_url, content, content_type=content_type)
        if not operation_url:
            return None
        result = self._poll_result(operation_url)
        if not result:
            return None
        return self._document_extraction(result, content_type=content_type)

    def _document_extraction(self, result: Mapping[str, object], *, content_type: str) -> DocumentExtraction | None:
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
            content_type=content_type,
            extraction_method="azure_document_intelligence",
            page_count=page_count,
            confidence=confidence,
        )

    def _post_analyze(self, url: str, payload: bytes, *, content_type: str = "application/json") -> str | None:
        req = request.Request(url, data=payload, method="POST")
        req.add_header("Ocp-Apim-Subscription-Key", self.api_key)
        req.add_header("Content-Type", content_type)
        try:
            with request.urlopen(req, timeout=20) as response:
                return response.headers.get("Operation-Location")
        except (error.HTTPError, error.URLError, TimeoutError, ValueError):
            return None

    def _download_document(self, document_url: str) -> tuple[bytes, str] | None:
        if not safe_public_document_url(document_url):
            return None
        req = request.Request(document_url)
        req.add_header("User-Agent", "AllerNavMenuBot/1.0")
        try:
            with request.urlopen(req, timeout=15) as response:
                content = response.read(MAX_DOCUMENT_BYTES + 1)
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
        except (error.HTTPError, error.URLError, TimeoutError, ValueError):
            return None
        if not content or len(content) > MAX_DOCUMENT_BYTES:
            return None
        resolved_type = content_type or document_content_type(document_url)
        if resolved_type != "application/pdf" and not resolved_type.startswith("image/"):
            return None
        return content, resolved_type

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


def safe_public_document_url(document_url: str) -> bool:
    try:
        parsed = parse.urlparse(document_url)
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror:
        return False
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            return False
    return True
