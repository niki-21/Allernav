from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .langchain_tracing import invoke_traced_runnable, update_current_trace_metadata
from .models import MenuItem, MenuSection


class ExtractedDish(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    price: str | None = Field(default=None, max_length=40)


class ExtractedSection(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    items: list[ExtractedDish] = Field(default_factory=list)


class ExtractedMenuPage(BaseModel):
    sections: list[ExtractedSection] = Field(default_factory=list)


StructuredInvoker = Callable[[list[tuple[str, str]]], ExtractedMenuPage | dict[str, Any]]


def azure_openai_menu_extraction_configured() -> bool:
    return bool(
        os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        and os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        and os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
    )


def extract_english_menu_page(
    *,
    ocr_text: str,
    source_url: str,
    source_page: int,
    ocr_confidence: float | None,
    restaurant_id: str | None = None,
    invoker: StructuredInvoker | None = None,
) -> list[MenuSection]:
    if not ocr_text.strip():
        return []
    invoke = invoker or _langchain_invoker()
    if invoke is None:
        return []
    messages = [
        (
            "system",
            "You extract English restaurant menu evidence from OCR. Return only dishes explicitly present in the "
            "provided text. Keep dish names, descriptions, and prices faithful to the source. Ignore non-English "
            "text, marketing copy, addresses, hours, and allergy disclaimers. Do not translate, infer ingredients, "
            "or make safety claims.",
        ),
        ("human", f"OCR page {source_page}:\n\n{ocr_text[:24000]}"),
    ]
    def normalize(input_messages: list[tuple[str, str]]) -> list[MenuSection]:
        for _attempt in range(2):
            try:
                result = invoke(input_messages)
                page = result if isinstance(result, ExtractedMenuPage) else ExtractedMenuPage.model_validate(result)
                sections = _grounded_sections(
                    page,
                    ocr_text=ocr_text,
                    source_url=source_url,
                    source_page=source_page,
                    ocr_confidence=ocr_confidence,
                )
                update_current_trace_metadata(item_count=sum(len(section.items) for section in sections))
                return sections
            except (ValidationError, TypeError, ValueError):
                continue
        update_current_trace_metadata(item_count=0)
        return []

    return invoke_traced_runnable(
        name="AllerNav Menu Normalization",
        value=messages,
        func=normalize,
        metadata={
            "restaurant_id": restaurant_id,
            "source_url": source_url,
            "ocr_page": source_page,
            "ocr_confidence": ocr_confidence,
        },
    )


def _langchain_invoker() -> StructuredInvoker | None:
    if not azure_openai_menu_extraction_configured():
        return None
    try:
        from langchain_openai import AzureChatOpenAI
    except ImportError:
        return None
    model = AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "").strip(),
        api_key=os.getenv("AZURE_OPENAI_API_KEY", "").strip(),
        azure_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip(),
        api_version=os.getenv(
            "AZURE_OPENAI_CHAT_API_VERSION",
            os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        ),
        temperature=0,
        max_retries=1,
    )
    structured = model.with_structured_output(ExtractedMenuPage, method="json_schema")
    return structured.invoke


def _grounded_sections(
    page: ExtractedMenuPage,
    *,
    ocr_text: str,
    source_url: str,
    source_page: int,
    ocr_confidence: float | None,
) -> list[MenuSection]:
    sections: list[MenuSection] = []
    for section in page.sections:
        items: list[MenuItem] = []
        for dish in section.items:
            if not _has_english_words(dish.name) or not _grounded(dish.name, ocr_text, threshold=0.6):
                continue
            if dish.description and not _grounded(dish.description, ocr_text, threshold=0.3):
                continue
            if dish.price and not _price_grounded(dish.price, ocr_text):
                continue
            items.append(
                MenuItem(
                    name=dish.name.strip(),
                    description=dish.description.strip() if dish.description else None,
                    price=dish.price.strip() if dish.price else None,
                    source_page=source_page,
                    source_url=source_url,
                    ocr_confidence=ocr_confidence,
                )
            )
        if items:
            title = section.title.strip() if _has_english_words(section.title) else "Menu"
            sections.append(MenuSection(title=title, items=items))
    return sections


def _has_english_words(value: str) -> bool:
    return re.search(r"\b[A-Za-z]{2,}\b", value) is not None


def _grounded(value: str, source: str, *, threshold: float) -> bool:
    source_tokens = set(_tokens(source))
    value_tokens = [token for token in _tokens(value) if len(token) > 2]
    if not value_tokens:
        return False
    matched = sum(token in source_tokens for token in value_tokens)
    return matched / len(value_tokens) >= threshold


def _price_grounded(price: str, source: str) -> bool:
    expected = re.sub(r"[^0-9.]", "", price)
    return bool(expected and expected in re.sub(r"[^0-9.]", "", source))


def _tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9]+", normalized)
