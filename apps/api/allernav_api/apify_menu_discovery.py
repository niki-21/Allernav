from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


Requester = Callable[[str, dict[str, str], dict[str, Any], dict[str, str], float], Any]

DEFAULT_APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_APIFY_MENU_DISCOVERY_ACTOR = "apify~playwright-scraper"


@dataclass(frozen=True)
class RenderedMenuPage:
    url: str
    title: str | None
    visible_text: str


@dataclass(frozen=True)
class RenderedMenuDiscovery:
    urls: list[str]
    pages: list[RenderedMenuPage]
    error: str | None = None


def menu_discovery_page_function() -> str:
    wait_ms = rendered_wait_ms()
    return r"""
async function pageFunction(context) {
    const { page, request } = context;
    await page.waitForTimeout(__WAIT_MS__);

    for (let pass = 0; pass < 3; pass += 1) {
        const controls = page.getByText(/load more content|load more|show more|view more/i, { exact: false });
        const count = Math.min(await controls.count().catch(() => 0), 4);
        if (!count) break;
        let clicked = 0;
        for (let index = 0; index < count; index += 1) {
            const control = controls.nth(index);
            if (await control.isVisible().catch(() => false)) {
                await control.click({ timeout: 1500 }).catch(() => null);
                clicked += 1;
            }
        }
        if (!clicked) break;
        await page.waitForTimeout(800);
    }

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
""".replace("__WAIT_MS__", str(wait_ms))


class ApifyMenuDiscoveryError(Exception):
    pass


def apify_menu_discovery_configured() -> bool:
    token = os.getenv("APIFY_TOKEN", "").strip()
    enabled = os.getenv("APIFY_MENU_DISCOVERY_ENABLED", "true").strip().lower()
    return bool(token and enabled not in {"0", "false", "no", "off"})


def request_timeout_seconds() -> float:
    raw = os.getenv("APIFY_MENU_DISCOVERY_TIMEOUT_SECONDS", os.getenv("APIFY_TIMEOUT_SECONDS", "45"))
    try:
        return float(min(90, max(3, float(raw))))
    except ValueError:
        return 45.0


def rendered_wait_ms() -> int:
    raw = os.getenv("APIFY_MENU_DISCOVERY_WAIT_MS", "2500")
    try:
        return max(500, min(10_000, int(raw)))
    except ValueError:
        return 2500


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
    return discover_rendered_menu_evidence(website_url, requester=requester).urls


def discover_rendered_menu_evidence(
    website_url: str,
    *,
    requester: Requester | None = None,
    candidate_urls: list[str] | None = None,
    timeout_seconds: float | None = None,
) -> RenderedMenuDiscovery:
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token or os.getenv("APIFY_MENU_DISCOVERY_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return RenderedMenuDiscovery(urls=[], pages=[])

    base_url = os.getenv("APIFY_API_BASE_URL", DEFAULT_APIFY_BASE_URL).strip() or DEFAULT_APIFY_BASE_URL
    actor = os.getenv("APIFY_MENU_DISCOVERY_ACTOR", DEFAULT_APIFY_MENU_DISCOVERY_ACTOR).strip()
    actor_path = quote(actor.replace("/", "~"), safe="~")
    url = f"{base_url.rstrip('/')}/actors/{actor_path}/run-sync-get-dataset-items"
    body = build_apify_menu_discovery_input(website_url, candidate_urls=candidate_urls)
    timeout = (
        request_timeout_seconds()
        if timeout_seconds is None
        else max(3.0, min(request_timeout_seconds(), timeout_seconds))
    )

    try:
        payload = (requester or default_requester)(
            url,
            {},
            body,
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout,
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise ApifyMenuDiscoveryError(str(exc)) from exc

    return parse_rendered_menu_discovery(payload)


def build_apify_menu_discovery_input(
    website_url: str,
    *,
    candidate_urls: list[str] | None = None,
) -> dict[str, Any]:
    start_urls: list[str] = []
    for candidate in [*(candidate_urls or []), website_url]:
        if candidate.startswith(("http://", "https://")) and candidate not in start_urls:
            start_urls.append(candidate)
        if len(start_urls) >= max_pages_per_crawl():
            break
    return {
        "startUrls": [{"url": url} for url in start_urls],
        "linkSelector": "a[href]",
        "maxRequestsPerCrawl": max_pages_per_crawl(),
        "maxRequestRetries": 0,
        "pageLoadTimeoutSecs": 30,
        "pageFunctionTimeoutSecs": 30,
        "waitUntil": "domcontentloaded",
        "downloadMedia": False,
        "downloadCss": True,
        "headless": True,
        "proxyConfiguration": {"useApifyProxy": True},
        "pageFunction": menu_discovery_page_function(),
    }


def parse_rendered_menu_urls(payload: Any) -> list[str]:
    return parse_rendered_menu_discovery(payload).urls


def parse_rendered_menu_discovery(payload: Any) -> RenderedMenuDiscovery:
    urls: list[str] = []
    pages: list[RenderedMenuPage] = []
    for item in flatten_items(payload):
        for candidate in extract_urls_from_item(item):
            if candidate not in urls and looks_like_menu_candidate(candidate):
                urls.append(candidate)
        page = extract_rendered_page(item)
        if page:
            pages.append(page)
    return RenderedMenuDiscovery(urls=urls[:20], pages=pages[:5])


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


def extract_rendered_page(item: dict[str, Any]) -> RenderedMenuPage | None:
    url = item.get("url")
    visible_text = item.get("visibleText") or item.get("visible_text") or item.get("text")
    title = item.get("title")
    if not isinstance(url, str) or not isinstance(visible_text, str):
        return None
    cleaned = visible_text.strip()
    if len(cleaned) < 40:
        return None
    if not looks_like_rendered_menu_text(cleaned):
        return None
    return RenderedMenuPage(
        url=url,
        title=title if isinstance(title, str) else None,
        visible_text=cleaned,
    )


def looks_like_rendered_menu_text(text: str) -> bool:
    normalized = text.lower()
    has_menu_word = any(word in normalized for word in ("menu", "dinner", "lunch", "brunch", "appetizer", "entree"))
    has_food_word = any(
        word in normalized
        for word in (
            "chicken",
            "shrimp",
            "salad",
            "pasta",
            "sandwich",
            "burger",
            "rice",
            "sauce",
            "cheese",
            "taco",
            "roll",
        )
    )
    return has_menu_word and (has_food_word or "$" in normalized)


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
