from __future__ import annotations

import html
import json
import os
import re
import sqlite3
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from . import supabase_store
from .document_intelligence import (
    DocumentExtraction,
    document_content_type,
    extract_document_from_url,
    looks_like_document_url,
)
from .models import EvidenceFragment, MenuItem, MenuSection, MenuSource, PlaceMenu, SourceType
from .risk_engine import is_prompt_injection, parse_raw_menu_text


FetchHtml = Callable[[str], str | None]
ExtractDocument = Callable[[str], DocumentExtraction | None]

MENU_NAVIGATION_WORDS = {
    "home",
    "hours",
    "hour",
    "reservation",
    "reservations",
    "order",
    "locations",
    "directions",
    "about",
    "contact",
    "careers",
    "privacy",
    "terms",
    "press",
    "gallery",
    "merch",
}

SCHEDULE_WORDS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "mon",
    "tue",
    "wed",
    "thu",
    "fri",
    "sat",
    "sun",
    "am",
    "pm",
    "open",
    "closed",
    "hours",
    "hour",
    "calendar",
    "event",
    "events",
    "market",
}

BEVERAGE_ONLY_WORDS = {
    "beer",
    "wine",
    "cocktail",
    "cocktails",
    "drink",
    "drinks",
    "soda",
    "coffee",
    "tea",
    "spezi",
    "cola",
    "lemonade",
    "espresso",
    "latte",
    "cappuccino",
    "lager",
    "ale",
    "ipa",
    "pilsner",
}

NON_DISH_SECTION_WORDS = {
    "about",
    "contact",
    "events",
    "gallery",
    "hours",
    "locations",
    "private events",
    "reservations",
    "visit",
}

PROMO_OR_DEAL_WORDS = {
    "combo",
    "deal",
    "deals",
    "value",
    "meal",
    "meals",
    "bundle",
    "bundles",
    "special",
    "specials",
    "starting",
    "starts",
}

PREPARATION_ONLY_WORDS = {
    "sauced",
    "fried",
    "grilled",
    "roasted",
    "steamed",
    "crispy",
    "baked",
    "spicy",
    "mild",
    "hot",
}

def default_db_path() -> Path:
    configured = os.getenv("ALLERNAV_MENU_DB")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / ".data" / "menu_ingestion.sqlite"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_records (
            restaurant_id TEXT PRIMARY KEY,
            restaurant_name TEXT,
            source_url TEXT,
            source_type TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            raw_text TEXT,
            menu_json TEXT NOT NULL
        )
        """
    )
    return connection


def save_menu_source(
    *,
    restaurant_id: str,
    restaurant_name: str | None,
    source: MenuSource,
    status: str = "complete",
    error_message: str | None = None,
    db_path: Path | None = None,
) -> None:
    fetched_at = source.source_timestamp or datetime.now(UTC).isoformat()
    supabase_store.save_menu_source(
        restaurant_id=restaurant_id,
        restaurant_name=restaurant_name,
        source=source,
        status=status,
        error_message=error_message,
    )
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO menu_records (
                restaurant_id, restaurant_name, source_url, source_type,
                fetched_at, status, error, raw_text, menu_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(restaurant_id) DO UPDATE SET
                restaurant_name=excluded.restaurant_name,
                source_url=excluded.source_url,
                source_type=excluded.source_type,
                fetched_at=excluded.fetched_at,
                status=excluded.status,
                error=excluded.error,
                raw_text=excluded.raw_text,
                menu_json=excluded.menu_json
            """,
            (
                restaurant_id,
                restaurant_name,
                source.source_url,
                source.source_type.value,
                fetched_at,
                status,
                error_message,
                source.raw_text,
                source.model_dump_json(),
            ),
        )


def load_menu_record(restaurant_id: str, db_path: Path | None = None) -> tuple[str | None, MenuSource] | None:
    supabase_record = supabase_store.load_menu_source(restaurant_id)
    if supabase_record:
        restaurant_name, source = supabase_record
        sanitized_sections = sanitize_sections(source.sections)
        if sanitized_sections:
            return restaurant_name, source.model_copy(
                update={
                    "sections": sanitized_sections,
                    "raw_text": summarize_menu_text(sanitized_sections) or None,
                }
            )

    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT restaurant_name, menu_json, status FROM menu_records WHERE restaurant_id = ?",
            (restaurant_id,),
        ).fetchone()

    if not row or row[2] != "complete":
        return None
    source = MenuSource.model_validate_json(row[1])
    sanitized_sections = sanitize_sections(source.sections)
    if not sanitized_sections:
        return None
    return row[0], source.model_copy(
        update={
            "sections": sanitized_sections,
            "raw_text": summarize_menu_text(sanitized_sections) or None,
        }
    )


def load_menu_source(restaurant_id: str, db_path: Path | None = None) -> MenuSource | None:
    record = load_menu_record(restaurant_id, db_path)
    if not record:
        return None
    return record[1]


def load_place_menu(restaurant_id: str, db_path: Path | None = None) -> PlaceMenu:
    source = load_menu_source(restaurant_id, db_path)
    if not source:
        return PlaceMenu(place_id=restaurant_id, status="missing")
    return PlaceMenu(
        place_id=restaurant_id,
        source_url=source.source_url,
        source_fetched_at=source.source_timestamp,
        status="complete",
        sections=source.sections,
    )


def stored_evidence(restaurant_id: str, db_path: Path | None = None) -> list[EvidenceFragment]:
    source = load_menu_source(restaurant_id, db_path)
    if not source:
        return []

    fragments: list[EvidenceFragment] = []
    for section in source.sections:
        for item in section.items:
            text = f"{item.name}: {item.description}" if item.description else item.name
            fragments.append(
                EvidenceFragment(
                    id=f"stored-{restaurant_id}-{len(fragments)}",
                    source_type=source.source_type,
                    source_url=source.source_url,
                    source_timestamp=source.source_timestamp,
                    dish_name=item.name,
                    text=text,
                    reliability=source.reliability,
                )
            )
    return fragments


def ingest_menu_from_website(
    *,
    restaurant_id: str,
    restaurant_name: str | None,
    website_url: str,
    fetch_html: FetchHtml | None = None,
    extract_document: ExtractDocument | None = None,
    db_path: Path | None = None,
) -> MenuSource:
    fetcher = fetch_html or fetch_html_url
    document_extractor = extract_document or extract_document_from_url
    candidate_urls = discover_candidate_urls(website_url, fetcher)
    last_source: MenuSource | None = None

    for candidate_url in candidate_urls:
        if looks_like_document_url(candidate_url):
            source = parse_menu_document(candidate_url, document_extractor)
            last_source = source
            if source.sections:
                save_menu_source(
                    restaurant_id=restaurant_id,
                    restaurant_name=restaurant_name,
                    source=source,
                    db_path=db_path,
                )
                return source
            continue

        page = fetcher(candidate_url)
        if not page:
            continue
        source = parse_menu_html(page, candidate_url)
        last_source = source
        if source.sections:
            save_menu_source(
                restaurant_id=restaurant_id,
                restaurant_name=restaurant_name,
                source=source,
                db_path=db_path,
            )
            return source

    failed_source = last_source or MenuSource(
        source_type=SourceType.RESTAURANT_WEBSITE,
        source_url=website_url,
        source_timestamp=datetime.now(UTC).isoformat(),
        reliability=0.7,
        raw_text=None,
        sections=[],
    )
    save_menu_source(
        restaurant_id=restaurant_id,
        restaurant_name=restaurant_name,
        source=failed_source,
        status="failed",
        error_message="No structured menu items were extracted from official website pages.",
        db_path=db_path,
    )
    return failed_source


def discover_candidate_urls(website_url: str, fetch_html: FetchHtml | None = None) -> list[str]:
    normalized = normalize_url(website_url)
    if not normalized:
        return []

    candidates = [normalized]
    fetcher = fetch_html or fetch_html_url
    homepage = fetcher(normalized)
    if homepage:
        for url in extract_candidate_menu_urls(homepage, normalized):
            if url not in candidates:
                candidates.append(url)
    return candidates[:4]


def fetch_html_url(url: str) -> str | None:
    normalized = normalize_url(url)
    if not normalized:
        return None
    req = request.Request(normalized)
    req.add_header("User-Agent", "AllerNavMenuBot/1.0 (+https://allernav.local)")
    req.add_header("Accept", "text/html,application/xhtml+xml")
    try:
        with request.urlopen(req, timeout=10) as response:
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return None
            return response.read().decode("utf-8", errors="ignore")
    except (error.HTTPError, error.URLError, TimeoutError, ValueError):
        return None


def parse_menu_html(html_text: str, source_url: str) -> MenuSource:
    timestamp = datetime.now(UTC).isoformat()
    sections = sanitize_sections(parse_json_ld_menus(html_text) + parse_visible_html_menu(html_text))
    raw_text = summarize_menu_text(sections)
    return MenuSource(
        source_type=SourceType.RESTAURANT_WEBSITE,
        source_url=source_url,
        source_timestamp=timestamp,
        reliability=0.78 if sections else 0.35,
        raw_text=raw_text or None,
        sections=sections,
    )


def parse_menu_document(document_url: str, extract_document: ExtractDocument | None = None) -> MenuSource:
    timestamp = datetime.now(UTC).isoformat()
    extractor = extract_document or extract_document_from_url
    extraction = extractor(document_url)
    if not extraction:
        return MenuSource(
            source_type=SourceType.OFFICIAL_MENU,
            source_url=document_url,
            source_timestamp=timestamp,
            reliability=0.2,
            raw_text=None,
            sections=[],
            content_type=document_content_type(document_url),
            document_url=document_url,
            extraction_method="azure_document_intelligence",
        )

    sections = sanitize_sections(parse_raw_menu_text(extraction.content))
    confidence = extraction.confidence if extraction.confidence is not None else 0.55
    reliability = round(min(0.76, max(0.22, confidence)), 2) if sections else 0.22
    return MenuSource(
        source_type=SourceType.OFFICIAL_MENU,
        source_url=document_url,
        source_timestamp=timestamp,
        reliability=reliability,
        raw_text=summarize_menu_text(sections) or None,
        sections=sections,
        content_type=extraction.content_type,
        document_url=document_url,
        extraction_method=extraction.extraction_method,
        page_count=extraction.page_count,
        extraction_confidence=extraction.confidence,
    )


def parse_json_ld_menus(html_text: str) -> list[MenuSection]:
    sections: list[MenuSection] = []
    for raw_json in re.findall(
        r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>([\s\S]*?)</script>",
        html_text,
        flags=re.IGNORECASE,
    ):
        try:
            payload = json.loads(html.unescape(raw_json.strip()))
        except json.JSONDecodeError:
            continue
        for node in flatten_json_ld(payload):
            sections.extend(extract_menu_sections(node))
    return sections


def parse_visible_html_menu(html_text: str) -> list[MenuSection]:
    cleaned = re.sub(r"<(script|style|nav|footer|header)[^>]*>[\s\S]*?</\1>", "\n", html_text, flags=re.IGNORECASE)
    blocks = re.findall(r"<(?:article|li|div|section)[^>]*(?:menu|item|dish)[^>]*>([\s\S]*?)</(?:article|li|div|section)>", cleaned, flags=re.IGNORECASE)
    items: list[MenuItem] = []

    for block in blocks:
        name = first_tag_text(block, ("h2", "h3", "h4", "strong"))
        description = first_tag_text(block, ("p", "span"))
        if not name:
            continue
        item = build_menu_item(name, description)
        if item:
            items.append(item)

    if not items:
        text = html_to_text(cleaned)
        sections = parse_raw_menu_text("\n".join(line for line in text.splitlines() if not is_prompt_injection(line)))
        return sanitize_sections(sections)

    return [MenuSection(title="Extracted menu", items=items)]


def extract_candidate_menu_urls(html_text: str, base_url: str) -> list[str]:
    urls: list[str] = []
    for href, label in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>", html_text, flags=re.IGNORECASE):
        text = html_to_text(label).lower()
        target = href.lower()
        absolute = absolute_url(href, base_url)
        if not re.search(r"menu|food|dinner|lunch|brunch|order", f"{target} {text}") and not looks_like_document_url(absolute):
            continue
        if absolute and absolute not in urls:
            urls.append(absolute)
    return urls


def extract_menu_sections(value: Any, fallback_title: str = "Menu") -> list[MenuSection]:
    if isinstance(value, list):
        return [section for entry in value for section in extract_menu_sections(entry, fallback_title)]
    if not isinstance(value, dict):
        return []

    schema_type = schema_types(value)
    title = clean_text(value.get("name")) or fallback_title
    candidates = [
        value.get("hasMenuSection"),
        value.get("hasMenuItem"),
        value.get("hasPart"),
        value.get("mainEntity"),
        value.get("menuSection"),
        value.get("menu"),
    ]
    child_values = flatten_candidates(candidates)
    child_sections = [section for child in child_values for section in extract_menu_sections(child, title)]
    child_items = [item for child in child_values if (item := extract_menu_item(child))]

    if "menusection" in schema_type or child_items:
        return [
            *child_sections,
            MenuSection(title=title, items=dedupe_items(child_items)),
        ] if child_items else child_sections

    if "menu" in schema_type:
        return child_sections
    return child_sections


def extract_menu_item(value: Any) -> MenuItem | None:
    if not isinstance(value, dict):
        return None
    schema_type = schema_types(value)
    name = clean_text(value.get("name"))
    description = clean_text(value.get("description"))
    offers = value.get("offers") if isinstance(value.get("offers"), dict) else {}
    price = clean_text(value.get("price")) or clean_text(offers.get("price")) if isinstance(offers, dict) else None

    if "menuitem" not in schema_type and not (name and description):
        return None
    if not name:
        return None
    return build_menu_item(name, description, price)


def build_menu_item(name: str, description: str | None = None, price: str | None = None) -> MenuItem | None:
    name = clean_text(name) or ""
    description = clean_text(description)
    if not looks_like_real_menu_item(name, description):
        return None
    return MenuItem(name=name, description=description, price=clean_text(price))


def sanitize_sections(sections: Iterable[MenuSection]) -> list[MenuSection]:
    cleaned: list[MenuSection] = []
    seen_sections: set[str] = set()
    for section in sections:
        title = clean_text(section.title) or "Menu"
        if is_non_dish_section_title(title):
            continue
        key = title.lower()
        items = dedupe_items(item for item in section.items if looks_like_real_menu_item(item.name, item.description))
        if not items or key in seen_sections:
            continue
        seen_sections.add(key)
        cleaned.append(MenuSection(title=title, items=items[:30]))
    return cleaned[:8]


def looks_like_real_menu_item(name: str, description: str | None = None) -> bool:
    if is_prompt_injection(name) or (description and is_prompt_injection(description)):
        return False
    normalized = name.lower()
    description_normalized = (description or "").lower()
    combined = f"{normalized} {description_normalized}"
    terms = re.split(r"[^a-z0-9]+", normalized)
    if len(name) < 3 or len(name) > 80:
        return False
    if sum(1 for word in MENU_NAVIGATION_WORDS if word in terms) >= 2:
        return False
    if re.search(r"privacy|copyright|newsletter|instagram|facebook|careers|gift card", normalized):
        return False
    if looks_like_schedule_or_event_text(name, description):
        return False
    if looks_like_non_dish_marketing_text(name, description):
        return False
    if looks_like_meal_deal_or_promo(name, description):
        return False
    if looks_like_preparation_phrase_without_dish(name, description):
        return False
    if len([term for term in terms if term]) <= 1 and not description:
        return False
    return menu_item_quality_score(name, description) >= 4


def menu_item_quality_score(name: str, description: str | None = None) -> int:
    normalized = name.lower()
    description_normalized = (description or "").lower()
    combined = f"{normalized} {description_normalized}"
    terms = [term for term in re.split(r"[^a-z0-9]+", normalized) if term]
    score = 0

    if 2 <= len(terms) <= 7:
        score += 1
    if description and 8 <= len(description) <= 180:
        score += 2
    if looks_like_food_text(combined):
        score += 2
    if re.search(r"\$\d|\b\d{1,3}\.\d{2}\b", combined):
        score += 1
    if re.search(r"\b(with|served|over|topped|sauce|contains|ingredient|ingredients)\b", combined):
        score += 1
    if re.search(r"\b(menu|plate|bowl|sandwich|salad|roll|taco|burger|pizza|pasta|noodle|soup|entree)\b", combined):
        score += 1

    if is_beverage_only(name, description):
        score -= 3
    if re.search(r"\b(hours?|open|closed|event|events|calendar|reservation|book|order online|located)\b", combined):
        score -= 3
    if re.search(r"\b(gift cards?|newsletter|follow us|learn more|read more|sign up|subscribe|directions)\b", combined):
        score -= 3
    if re.search(r"\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", combined):
        score -= 2
    return score


def is_non_dish_section_title(title: str) -> bool:
    normalized = title.lower().strip()
    return normalized in NON_DISH_SECTION_WORDS or bool(
        re.search(r"\b(hours?|events?|reservations?|contact|location|gallery|press)\b", normalized)
    )


def looks_like_non_dish_marketing_text(name: str, description: str | None = None) -> bool:
    text = f"{name} {description or ''}".lower()
    if re.search(r"\b(gift cards?|newsletter|follow us|instagram|facebook|tiktok|careers|privacy|terms)\b", text):
        return True
    if re.search(r"\b(order online|book now|reserve|make a reservation|view menu|download menu)\b", text):
        return True
    if re.search(r"\b(private events?|catering inquiries|press inquiries|located at|visit us)\b", text):
        return True
    if re.search(r"\b(our|we|us|story|vision|began|founded|artist|craft|crave-able|ultimate)\b", text) and not re.search(
        r"\$\d|\b\d{1,3}\.\d{2}\b",
        text,
    ):
        return True
    return False


def looks_like_meal_deal_or_promo(name: str, description: str | None = None) -> bool:
    normalized_name = name.lower()
    text = f"{name} {description or ''}".lower()
    tokens = set(re.split(r"[^a-z0-9]+", text))
    has_price = bool(re.search(r"\$\d|\b\d{1,3}\.\d{2}\b", text))
    has_food_noun = has_menu_item_noun(text)

    if re.fullmatch(r"\d+\s+(for|fo)\s+\w+", normalized_name):
        return True
    if re.search(r"\b\d+\s+for\s+\w+\b", normalized_name) and not has_food_noun:
        return True
    if any(word in tokens for word in PROMO_OR_DEAL_WORDS) and re.search(
        r"\b(pick|choose|select|get|starting at|best value|beverage|starter|main)\b",
        text,
    ):
        return True
    if has_price and re.search(r"\b(starting at|value meal|pick your|beverage,?\s+starter|main)\b", text) and not has_food_noun:
        return True
    return False


def looks_like_preparation_phrase_without_dish(name: str, description: str | None = None) -> bool:
    normalized_name = name.lower()
    text = f"{name} {description or ''}".lower()
    tokens = [term for term in re.split(r"[^a-z0-9]+", normalized_name) if term]
    if not tokens:
        return False
    prep_token_count = sum(1 for token in tokens if token in PREPARATION_ONLY_WORDS or token in {"or", "and"})
    if prep_token_count >= len(tokens) - 1 and not has_menu_item_noun(text):
        return True
    if re.fullmatch(r"(sauced|fried|grilled|roasted|steamed|crispy)(,\s*|\s+or\s+|\s+and\s+).+", normalized_name):
        return not has_menu_item_noun(text)
    return False


def is_beverage_only(name: str, description: str | None = None) -> bool:
    text = f"{name} {description or ''}".lower()
    tokens = set(re.split(r"[^a-z0-9]+", text))
    has_beverage = any(word in tokens for word in BEVERAGE_ONLY_WORDS)
    if not has_beverage:
        return False
    food_without_beverage = re.sub(
        r"\b(beer|wine|cocktails?|drinks?|drink|soda|coffee|tea|spezi|cola|lemonade|espresso|latte|cappuccino|lager|ale|ipa|pilsner|soft)\b",
        " ",
        text,
    )
    return not looks_like_food_text(food_without_beverage)


def looks_like_schedule_or_event_text(name: str, description: str | None = None) -> bool:
    text = f"{name} {description or ''}".lower()
    tokens = set(re.split(r"[^a-z0-9]+", text))
    time_pattern = re.search(r"\b\d{1,2}\s*(?::\d{2})?\s*(am|pm)\b|\b\d{1,2}\s*-\s*\d{1,2}\b", text)
    weekday_count = sum(1 for word in SCHEDULE_WORDS if word in tokens)
    if time_pattern and weekday_count > 0:
        return True
    if weekday_count >= 2 and not looks_like_food_text(text):
        return True
    if re.search(r"\b(open|closed|hours?|calendar|events?)\b", text) and time_pattern:
        return True
    return False


def looks_like_food_text(text: str) -> bool:
    return bool(
        re.search(
            r"\b("
            r"rice|bowl|noodle|noodles|pasta|sauce|sandwich|salad|roll|taco|burger|pizza|"
            r"chicken|beef|pork|fish|salmon|tuna|shrimp|crab|tofu|egg|cheese|cream|"
            r"sesame|peanut|soy|bread|flour|vegetable|tomato|greens|beans|soup|"
            r"cake|dessert|cookie|fries|fried|grilled|roasted|steamed|spicy|"
            r"dumpling|curry|kebab|falafel|hummus|gyro|steak|rib|wings|sausage"
            r")\b",
            text,
        )
    )


def has_menu_item_noun(text: str) -> bool:
    return bool(
        re.search(
            r"\b("
            r"bowl|noodle|noodles|pasta|sandwich|salad|roll|taco|burger|pizza|"
            r"chicken|beef|pork|fish|salmon|tuna|shrimp|crab|tofu|egg|eggs|cheese|"
            r"vegetable|tomato|greens|beans|soup|cake|dessert|cookie|cookies|fries|"
            r"dumpling|curry|kebab|falafel|hummus|gyro|steak|rib|ribs|wings|sausage|"
            r"burrito|quesadilla|nachos|toast|omelet|omelette|pancake|waffle|rice"
            r")\b",
            text,
        )
    )


def flatten_json_ld(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [node for entry in value for node in flatten_json_ld(entry)]
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            return [value, *graph]
        return [value]
    return []


def flatten_candidates(values: Iterable[Any]) -> list[Any]:
    output: list[Any] = []
    for value in values:
        if isinstance(value, list):
            output.extend(value)
        elif value is not None:
            output.append(value)
    return output


def schema_types(value: dict[str, Any]) -> str:
    raw_type = value.get("@type", "")
    if isinstance(raw_type, list):
        return " ".join(str(item).lower() for item in raw_type)
    return str(raw_type).lower()


def first_tag_text(block: str, tags: tuple[str, ...]) -> str | None:
    for tag in tags:
        match = re.search(rf"<{tag}[^>]*>([\s\S]*?)</{tag}>", block, flags=re.IGNORECASE)
        if match:
            value = clean_text(html_to_text(match.group(1)))
            if value:
                return value
    return None


def html_to_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</(?:p|div|li|article|section|h2|h3|h4)>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    lines = [clean_text(line) for line in html.unescape(value).splitlines()]
    return "\n".join(line for line in lines if line)


def clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = html.unescape(re.sub(r"\s+", " ", value)).strip()
    if not text or is_prompt_injection(text):
        return None
    return text


def dedupe_items(items: Iterable[MenuItem]) -> list[MenuItem]:
    seen: set[str] = set()
    output: list[MenuItem] = []
    for item in items:
        key = item.name.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def summarize_menu_text(sections: list[MenuSection]) -> str:
    lines = []
    for section in sections:
        for item in section.items[:20]:
            line = f"{item.name} - {item.description}" if item.description else item.name
            lines.append(line)
    return "\n".join(lines[:80])


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    candidate = url.strip()
    if not candidate:
        return None
    if not re.match(r"^https?://", candidate, flags=re.IGNORECASE):
        candidate = f"https://{candidate}"
    try:
        parsed = parse.urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return parse.urlunparse(parsed)


def absolute_url(candidate: str, base_url: str) -> str | None:
    try:
        return parse.urljoin(base_url, candidate)
    except ValueError:
        return None
