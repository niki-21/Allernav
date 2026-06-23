from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx


Requester = Callable[[str, dict[str, str], dict[str, Any], dict[str, str], float], Any]

DEFAULT_APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_APIFY_MENU_DISCOVERY_ACTOR = "apify~playwright-scraper"

MENU_DISCOVERY_PAGE_FUNCTION = r"""
async function pageFunction(context) {
    const { page, request } = context;
    await page.waitForTimeout(1500);

    const links = await page.$$eval('a[href]', (anchors) => anchors.map((anchor) => {
        const href = anchor.href;
        const text = (anchor.innerText || anchor.textContent || '').replace(/\s+/g, ' ').trim();
        return { href, text };
    }));

    const frames = page.frames().map((frame) => frame.url()).filter(Boolean);
    const title = await page.title().catch(() => '');
    const visibleText = await page.locator('body').innerText({ timeout: 3000 }).catch(() => '');

    return {
        url: request.url,
        title,
        links,
        frames,
        visibleText: visibleText.slice(0, 12000),
    };
}
"""


class ApifyMenuDiscoveryError(Exception):
    pass


def apify_menu_discovery_configured() -> bool:
    token = os.getenv("APIFY_TOKEN", "").strip()
    enabled = os.getenv("APIFY_MENU_DISCOVERY_ENABLED", "true").strip().lower()
    return bool(token and enabled not in {"0", "false", "no", "off"})


def request_timeout_seconds() -> float:
    raw = os.getenv("APIFY_MENU_DISCOVERY_TIMEOUT_SECONDS", os.getenv("APIFY_TIMEOUT_SECONDS", "18"))
    try:
        return float(min(30, max(3, float(raw))))
    except ValueError:
        return 18.0


def max_pages_per_crawl() -> int:
    raw = os.getenv("APIFY_MENU_DISCOVERY_MAX_PAGES", "4")
    try:
        return max(1, min(8, int(raw)))
    except ValueError:
        return 4


def default_requester(
    url: str,
    params: dict[str, str],
    body: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> Any:
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, params=params, json=body, headers=headers)
        response.raise_for_status()
        return response.json()


def discover_rendered_menu_urls(
    website_url: str,
    *,
    requester: Requester | None = None,
) -> list[str]:
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token or os.getenv("APIFY_MENU_DISCOVERY_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return []

    base_url = os.getenv("APIFY_API_BASE_URL", DEFAULT_APIFY_BASE_URL).strip() or DEFAULT_APIFY_BASE_URL
    actor = os.getenv("APIFY_MENU_DISCOVERY_ACTOR", DEFAULT_APIFY_MENU_DISCOVERY_ACTOR).strip()
    actor_path = quote(actor.replace("/", "~"), safe="~")
    url = f"{base_url.rstrip('/')}/actors/{actor_path}/run-sync-get-dataset-items"
    body = build_apify_menu_discovery_input(website_url)

    try:
        payload = (requester or default_requester)(
            url,
            {"token": token},
            body,
            {"Content-Type": "application/json"},
            request_timeout_seconds(),
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise ApifyMenuDiscoveryError(str(exc)) from exc

    return parse_rendered_menu_urls(payload)


def build_apify_menu_discovery_input(website_url: str) -> dict[str, Any]:
    return {
        "startUrls": [{"url": website_url}],
        "linkSelector": "a[href]",
        "maxRequestsPerCrawl": max_pages_per_crawl(),
        "maxRequestRetries": 1,
        "pageLoadTimeoutSecs": 20,
        "pageFunctionTimeoutSecs": 20,
        "waitUntil": "networkidle",
        "downloadMedia": False,
        "downloadCss": True,
        "headless": True,
        "proxyConfiguration": {"useApifyProxy": True},
        "pageFunction": MENU_DISCOVERY_PAGE_FUNCTION,
    }


def parse_rendered_menu_urls(payload: Any) -> list[str]:
    urls: list[str] = []
    for item in flatten_items(payload):
        for candidate in extract_urls_from_item(item):
            if candidate not in urls and looks_like_menu_candidate(candidate):
                urls.append(candidate)
    return urls[:20]


def flatten_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        output: list[dict[str, Any]] = []
        for item in payload:
            output.extend(flatten_items(item))
        return output
    if not isinstance(payload, dict):
        return []
    if any(key in payload for key in ("links", "frames", "url", "href", "menuUrls", "urls")):
        return [payload]
    output: list[dict[str, Any]] = []
    for key in ("items", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            output.extend(flatten_items(value))
    return output


def extract_urls_from_item(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("url", "href", "sourceUrl"):
        value = item.get(key)
        if isinstance(value, str):
            urls.append(value)
    for key in ("frames", "menuUrls", "urls"):
        value = item.get(key)
        if isinstance(value, list):
            urls.extend(entry for entry in value if isinstance(entry, str))
    links = item.get("links")
    if isinstance(links, list):
        for link in links:
            if isinstance(link, str):
                urls.append(link)
            elif isinstance(link, dict):
                href = link.get("href") or link.get("url")
                if isinstance(href, str):
                    urls.append(href)
    return urls


def looks_like_menu_candidate(url: str) -> bool:
    normalized = url.lower()
    if not normalized.startswith(("http://", "https://")):
        return False
    return any(
        term in normalized
        for term in (
            "menu",
            "menus",
            "food",
            "dinner",
            "lunch",
            "brunch",
            "order",
            "toasttab",
            "popmenu",
            "singleplatform",
            "chownow",
            ".pdf",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        )
    )
