from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


Requester = Callable[[str, float], Any]


@dataclass(frozen=True)
class WebMenuCandidate:
    url: str
    title: str | None = None
    snippet: str | None = None
    provider: str = "web_search"


def web_menu_discovery_configured() -> bool:
    return bool(
        (os.getenv("GOOGLE_SEARCH_API_KEY", "").strip() and os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip())
        or os.getenv("SERPAPI_API_KEY", "").strip()
    )


def discover_web_menu_candidates(
    *,
    restaurant_name: str | None,
    website_url: str | None = None,
    address: str | None = None,
    requester: Requester | None = None,
    time_budget_seconds: float | None = None,
) -> list[WebMenuCandidate]:
    if not restaurant_name:
        return []

    queries = build_menu_search_queries(restaurant_name=restaurant_name, website_url=website_url, address=address)
    deadline = time.monotonic() + time_budget_seconds if time_budget_seconds is not None else None
    candidates: list[WebMenuCandidate] = []
    for query in queries:
        if deadline is not None and time.monotonic() >= deadline:
            break
        for candidate in search_menu_web(query, requester=requester, deadline=deadline):
            if is_useful_menu_candidate(candidate.url) and candidate.url not in [item.url for item in candidates]:
                candidates.append(candidate)
        if len(candidates) >= 12:
            break
    return candidates[:12]


def build_menu_search_queries(
    *,
    restaurant_name: str,
    website_url: str | None = None,
    address: str | None = None,
) -> list[str]:
    name = restaurant_name.strip()
    location = f" {address.strip()}" if address else ""
    host = ""
    if website_url:
        try:
            parsed = parse.urlparse(website_url)
            host = parsed.netloc.removeprefix("www.")
        except ValueError:
            host = ""
    queries = [
        f'"{name}" menu pdf',
        f'"{name}" menu',
        f'"{name}" menu photo',
        f'"{name}" food menu{location}',
    ]
    if host:
        queries.insert(0, f'site:{host} (menu OR pdf OR jpg)')
        queries.insert(1, f'site:{host}/items/ "{name}"')
    return queries


def search_menu_web(
    query: str,
    *,
    requester: Requester | None = None,
    deadline: float | None = None,
) -> list[WebMenuCandidate]:
    google = search_google_programmable(query, requester=requester, timeout=remaining_request_timeout(deadline))
    if google:
        return google
    if deadline is not None and time.monotonic() >= deadline:
        return []
    return search_serpapi(query, requester=requester, timeout=remaining_request_timeout(deadline))


def search_google_programmable(
    query: str,
    *,
    requester: Requester | None = None,
    timeout: float | None = None,
) -> list[WebMenuCandidate]:
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY", "").strip()
    search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip()
    if not api_key or not search_engine_id:
        return []
    params = {
        "key": api_key,
        "cx": search_engine_id,
        "q": query,
        "num": "6",
        "safe": "active",
    }
    url = f"https://www.googleapis.com/customsearch/v1?{parse.urlencode(params)}"
    payload = request_json(url, requester=requester, timeout=timeout or search_request_timeout_seconds())
    if not isinstance(payload, dict):
        return []
    return parse_google_search_candidates(payload)


def search_serpapi(
    query: str,
    *,
    requester: Requester | None = None,
    timeout: float | None = None,
) -> list[WebMenuCandidate]:
    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not api_key:
        return []
    params = {
        "engine": "google",
        "api_key": api_key,
        "q": query,
        "num": "6",
        "safe": "active",
    }
    url = f"https://serpapi.com/search.json?{parse.urlencode(params)}"
    payload = request_json(url, requester=requester, timeout=timeout or search_request_timeout_seconds())
    if not isinstance(payload, dict):
        return []
    return parse_serpapi_candidates(payload)


def search_request_timeout_seconds() -> float:
    raw = os.getenv("WEB_MENU_SEARCH_TIMEOUT_SECONDS", "6")
    try:
        return max(1.0, min(12.0, float(raw)))
    except ValueError:
        return 6.0


def remaining_request_timeout(deadline: float | None) -> float:
    configured = search_request_timeout_seconds()
    if deadline is None:
        return configured
    return max(0.25, min(configured, deadline - time.monotonic()))


def request_json(url: str, *, requester: Requester | None = None, timeout: float = 6.0) -> Any:
    if requester:
        return requester(url, timeout)
    req = request.Request(url)
    req.add_header("User-Agent", "AllerNavMenuDiscovery/1.0")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
    except (error.HTTPError, error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def parse_google_search_candidates(payload: dict[str, Any]) -> list[WebMenuCandidate]:
    candidates: list[WebMenuCandidate] = []
    for item in payload.get("items", []):
        if not isinstance(item, dict) or not isinstance(item.get("link"), str):
            continue
        candidates.append(
            WebMenuCandidate(
                url=item["link"],
                title=item.get("title") if isinstance(item.get("title"), str) else None,
                snippet=item.get("snippet") if isinstance(item.get("snippet"), str) else None,
                provider="google_programmable_search",
            )
        )
        pagemap = item.get("pagemap")
        if isinstance(pagemap, dict):
            candidates.extend(image_candidates_from_pagemap(pagemap))
    return candidates


def image_candidates_from_pagemap(pagemap: dict[str, Any]) -> list[WebMenuCandidate]:
    candidates: list[WebMenuCandidate] = []
    for key in ("cse_image", "metatags"):
        values = pagemap.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            for url_key in ("src", "og:image", "twitter:image"):
                url = value.get(url_key)
                if isinstance(url, str):
                    candidates.append(WebMenuCandidate(url=url, provider="google_programmable_search_image"))
    return candidates


def parse_serpapi_candidates(payload: dict[str, Any]) -> list[WebMenuCandidate]:
    candidates: list[WebMenuCandidate] = []
    for item in payload.get("organic_results", []):
        if not isinstance(item, dict) or not isinstance(item.get("link"), str):
            continue
        candidates.append(
            WebMenuCandidate(
                url=item["link"],
                title=item.get("title") if isinstance(item.get("title"), str) else None,
                snippet=item.get("snippet") if isinstance(item.get("snippet"), str) else None,
                provider="serpapi",
            )
        )
    for item in payload.get("images_results", []):
        if isinstance(item, dict):
            original = item.get("original") or item.get("thumbnail")
            if isinstance(original, str):
                candidates.append(WebMenuCandidate(url=original, title=item.get("title"), provider="serpapi_image"))
    return candidates


def is_useful_menu_candidate(url: str) -> bool:
    try:
        parsed = parse.urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    normalized = url.lower()
    blocked_hosts = ("google.com", "gstatic.com", "facebook.com", "instagram.com", "tiktok.com", "youtube.com")
    if any(host in parsed.netloc.lower() for host in blocked_hosts):
        return False
    return any(
        token in normalized
        for token in (
            "menu",
            "menus",
            "/items/",
            "pdf",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            "toasttab",
            "popmenu",
            "singleplatform",
            "chownow",
        )
    )
